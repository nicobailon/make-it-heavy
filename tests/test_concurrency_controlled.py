"""Controlled concurrency tests with CPU protection."""
import pytest
import time
import threading
from unittest.mock import patch, MagicMock
from concurrent.futures import ThreadPoolExecutor
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator import TaskOrchestrator
from constants import TEST_MAX_CONCURRENT_AGENTS, TEST_MOCK_DELAY


def test_limited_parallel_agents(tmp_config):
    """Test with limited number of agents to avoid CPU overload."""
    # Given: Mock agent factory with controlled delay
    execution_times = []
    
    def mock_agent_factory(silent=False, **kwargs):
        agent = MagicMock()
        
        def mock_run(prompt):
            start = time.time()
            # Mock work with minimal delay
            time.sleep(TEST_MOCK_DELAY)
            execution_times.append(time.time() - start)
            return f"Response to: {prompt[:20]}"
        
        agent.run.side_effect = mock_run
        agent.tools = []
        agent.tool_mapping = {}
        return agent
    
    # When: Running with limited agents
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    orchestrator.num_agents = TEST_MAX_CONCURRENT_AGENTS  # Limited to 3
    
    with patch.object(orchestrator, 'decompose_task') as mock_decompose:
        mock_decompose.return_value = [f"Question {i}" for i in range(TEST_MAX_CONCURRENT_AGENTS)]
        
        start = time.time()
        result = orchestrator.orchestrate("Test limited concurrency")
        total_time = time.time() - start
    
    # Then: Executes in parallel but controlled
    # Note: execution_times includes the decomposition agent, so we expect +1
    assert len(execution_times) == TEST_MAX_CONCURRENT_AGENTS + 1
    assert total_time < TEST_MAX_CONCURRENT_AGENTS * TEST_MOCK_DELAY * 1.5  # Some parallelism
    assert "Response to:" in result


def test_thread_safety_with_minimal_agents():
    """Test thread safety with just 2 agents."""
    # Given: Shared state and lock
    shared_counter = 0
    lock = threading.Lock()
    
    def increment_safely():
        nonlocal shared_counter
        with lock:
            current = shared_counter
            # Simulate some work
            time.sleep(0.001)
            shared_counter = current + 1
    
    # When: Running increments in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(increment_safely) for _ in range(10)]
        for future in futures:
            future.result()
    
    # Then: All increments are accounted for
    assert shared_counter == 10


def test_orchestrator_progress_tracking_lightweight(tmp_config):
    """Test progress tracking with minimal agents."""
    # Given: Mock agent with progress updates
    progress_updates = []
    
    def mock_agent_factory(silent=False, **kwargs):
        agent = MagicMock()
        
        def mock_run(prompt):
            # Simulate some progress
            time.sleep(0.05)
            return "Done"
        
        agent.run.side_effect = mock_run
        agent.tools = []
        agent.tool_mapping = {}
        return agent
    
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    orchestrator.num_agents = 2  # Just 2 agents
    
    # Track progress updates
    original_update = orchestrator.update_agent_progress
    def track_update(agent_id, status, result=None):
        progress_updates.append((agent_id, status))
        original_update(agent_id, status, result)
    
    orchestrator.update_agent_progress = track_update
    
    # When: Running orchestration
    with patch.object(orchestrator, 'decompose_task') as mock_decompose:
        mock_decompose.return_value = ["Q1", "Q2"]
        orchestrator.orchestrate("Test progress")
    
    # Then: Progress was tracked
    assert len(progress_updates) > 0
    # Check we got updates for both agents
    agent_ids = set(update[0] for update in progress_updates)
    assert 0 in agent_ids
    assert 1 in agent_ids


def test_graceful_agent_failure_handling(tmp_config):
    """Test handling when one agent fails with minimal load."""
    # Given: Mix of successful and failing agents
    def mock_agent_factory(silent=False, **kwargs):
        agent = MagicMock()
        
        # Create a counter to track calls
        if not hasattr(mock_agent_factory, 'call_count'):
            mock_agent_factory.call_count = 0
        
        call_num = mock_agent_factory.call_count
        mock_agent_factory.call_count += 1
        
        if call_num == 2:  # Third agent fails
            agent.run.side_effect = Exception("Simulated failure")
        else:
            agent.run.return_value = f"Success from agent {call_num}"
        
        agent.tools = []
        agent.tool_mapping = {}
        return agent
    
    # Reset counter
    mock_agent_factory.call_count = 0
    
    # When: Running with 3 agents where one fails
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    orchestrator.num_agents = 3
    
    with patch.object(orchestrator, 'decompose_task') as mock_decompose:
        mock_decompose.return_value = ["Q1", "Q2", "Q3"]
        result = orchestrator.orchestrate("Test with failure")
    
    # Then: Still gets results from successful agents
    assert result is not None
    assert "Success from agent" in result or "failed" in result.lower()


@pytest.mark.slow
def test_resource_guard_cpu_check():
    """Test that we can check CPU usage (but don't actually stress it)."""
    try:
        import psutil
        
        # Get current CPU usage
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # This test just verifies we can check CPU
        assert isinstance(cpu_percent, (int, float))
        assert 0 <= cpu_percent <= 100
        
        # In real stress tests, we would skip if CPU > 80%
        if cpu_percent > 80:
            pytest.skip(f"CPU usage too high: {cpu_percent}%")
            
    except ImportError:
        # psutil not available, that's OK
        pass


def test_early_termination_on_completion(tmp_config):
    """Test that orchestrator stops early when all agents complete quickly."""
    # Given: Fast completing agents
    def fast_agent_factory(silent=False, **kwargs):
        agent = MagicMock()
        agent.run.return_value = "Quick response"
        agent.tools = []
        agent.tool_mapping = {}
        return agent
    
    # When: Running orchestration
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=fast_agent_factory)
    orchestrator.num_agents = 2
    
    with patch.object(orchestrator, 'decompose_task') as mock_decompose:
        mock_decompose.return_value = ["Q1", "Q2"]
        
        start = time.time()
        result = orchestrator.orchestrate("Quick test")
        duration = time.time() - start
    
    # Then: Completes very quickly
    assert duration < 1.0  # Should be nearly instant with mocks
    assert result is not None