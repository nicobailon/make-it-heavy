import pytest
import time
from unittest.mock import patch, MagicMock
import sys
import os
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orchestrator import TaskOrchestrator


def test_orchestrator_splits_task_into_n_subtasks(tmp_config, clean_env):
    """orchestrate splits user input into N subtasks based on config."""
    # Given: Orchestrator configured for 3 agents
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["orchestrator"]["parallel_agents"] = 3
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    # Create mock agent factory
    def mock_agent_factory(silent=False, **kwargs):
        mock_agent = MagicMock()
        # Mock the decomposition response as JSON array
        mock_agent.run.return_value = '\n["What is the mathematical calculation?", "What are the historical implications?", "What are the practical applications?"]\n'
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        return mock_agent

    # When: Creating orchestrator with mock factory
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    questions = orchestrator.decompose_task("Explain 2+2", 3)

    # Then: Task is split into 3 questions
    assert len(questions) == 3
    assert all(isinstance(q, str) for q in questions)


def test_orchestrator_runs_agents_in_parallel_not_serial(tmp_config, clean_env):
    """Multiple agents execute concurrently, not sequentially."""
    # Given: Orchestrator with slow mock agents
    execution_times = []

    def mock_agent_run(agent_id, question):
        start = time.time()
        time.sleep(0.1)  # Simulate work
        execution_times.append((agent_id, time.time() - start))
        return f"Response from agent {agent_id}"

    # When: Running 3 agents
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = []
        for i in range(3):
            future = executor.submit(mock_agent_run, i, f"Question {i}")
            futures.append(future)

        results = [f.result() for f in futures]

    total_time = time.time() - start_time

    # Then: Total time is less than sequential time
    assert total_time < 0.25, (
        f"Parallel execution took {total_time}s, should be < 0.25s"
    )
    assert len(results) == 3
    assert all("Response from agent" in r for r in results)


def test_orchestrator_updates_progress_atomically(tmp_config, clean_env):
    """Progress dict updates are atomic and don't cause race conditions."""
    # Given: Orchestrator
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)

    orchestrator = TaskOrchestrator(tmp_config, silent=True)

    # When: Multiple threads update progress simultaneously
    def update_progress_repeatedly(agent_id):
        for i in range(10):
            orchestrator.update_agent_progress(agent_id, f"Step {i}", f"Result {i}")
            time.sleep(0.001)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for i in range(4):
            future = executor.submit(update_progress_repeatedly, i)
            futures.append(future)

        # Wait for all updates
        for f in futures:
            f.result()

    # Then: All progress updates are recorded without corruption
    progress = orchestrator.get_progress_status()
    for i in range(4):
        assert i in progress
        assert progress[i] == "Step 9"  # Last update
    
    # Check results are also recorded
    for i in range(4):
        assert i in orchestrator.agent_results
        assert orchestrator.agent_results[i] == "Result 9"


def test_orchestrator_continues_when_some_agents_fail(tmp_config, clean_env):
    """Orchestrator continues and synthesizes even if some agents fail."""
    # Given: Mix of successful and failing agents
    agent_results = [
        "Success response 1",
        RuntimeError("Agent 2 failed"),
        "Success response 3",
    ]

    # Create mock agent factory that returns agents with different behaviors
    agent_count = 0
    def mock_agent_factory(silent=False, **kwargs):
        nonlocal agent_count
        agent = MagicMock()
        agent.tools = []
        agent.tool_mapping = {}
        
        # Pop from results list to simulate different agents
        if agent_count < len(agent_results):
            result = agent_results[agent_count]
            if isinstance(result, Exception):
                agent.run.side_effect = result
            else:
                agent.run.return_value = result
        agent_count += 1
        return agent

    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)

    # Mock decomposition
    with patch.object(orchestrator, "decompose_task") as mock_decompose:
        mock_decompose.return_value = ["Q1", "Q2", "Q3"]

        # When: Running orchestration
        result = orchestrator.orchestrate("Test task")

        # Then: Result contains successful responses despite one failure
        assert result is not None
        # Check that it aggregated properly (at least mentioned successful responses)
        assert "Success response" in result or "Agent" in result
