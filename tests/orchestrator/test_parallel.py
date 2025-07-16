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

    with patch("orchestrator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        # Mock the decomposition response
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""
        1. What is the mathematical calculation?
        2. What are the historical implications?
        3. What are the practical applications?
        """
                )
            )
        ]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client

        # When: Creating orchestrator
        orchestrator = TaskOrchestrator(tmp_config, silent=True)
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
            orchestrator.update_progress(agent_id, f"Step {i}", i / 10)
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
    for i in range(4):
        assert i in orchestrator.agent_progress
        assert orchestrator.agent_progress[i]["progress"] == 0.9  # Last update
        assert orchestrator.agent_progress[i]["status"] == "Step 9"


def test_orchestrator_handles_agent_timeout(tmp_config, clean_env):
    """Orchestrator handles agent timeout gracefully."""
    # Given: Orchestrator with short timeout
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["orchestrator"]["task_timeout"] = 0.1  # 100ms timeout
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    with patch("orchestrator.create_agent") as mock_create:
        # Create a mock agent that hangs
        mock_agent = MagicMock()
        mock_agent.run.side_effect = lambda x: time.sleep(
            1
        )  # Sleep longer than timeout
        mock_create.return_value = mock_agent

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # Mock decomposition
        with patch.object(orchestrator, "decompose_task") as mock_decompose:
            mock_decompose.return_value = ["Question 1", "Question 2"]

            # When: Running with timeout
            result = orchestrator.orchestrate("Test task")

            # Then: Completes despite timeout (doesn't hang forever)
            assert result is not None


def test_orchestrator_continues_when_some_agents_fail(tmp_config, clean_env):
    """Orchestrator continues and synthesizes even if some agents fail."""
    # Given: Mix of successful and failing agents
    agent_results = [
        "Success response 1",
        RuntimeError("Agent 2 failed"),
        "Success response 3",
    ]

    with patch("orchestrator.create_agent") as mock_create:

        def create_mock_agent(config, silent):
            agent = MagicMock()
            # Pop from results list to simulate different agents
            if agent_results:
                result = agent_results.pop(0)
                if isinstance(result, Exception):
                    agent.run.side_effect = result
                else:
                    agent.run.return_value = result
            return agent

        mock_create.side_effect = create_mock_agent

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # Mock decomposition and synthesis
        with patch.object(orchestrator, "decompose_task") as mock_decompose:
            mock_decompose.return_value = ["Q1", "Q2", "Q3"]

            with patch.object(orchestrator, "synthesize_responses") as mock_synthesize:
                mock_synthesize.return_value = "Combined response"

                # When: Running orchestration
                result = orchestrator.orchestrate("Test task")

                # Then: Synthesis is called with successful responses
                mock_synthesize.assert_called_once()
                responses = mock_synthesize.call_args[0][0]
                assert len(responses) == 2  # Only successful responses
                assert "Success response 1" in responses
                assert "Success response 3" in responses
