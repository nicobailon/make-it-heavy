"""Lightweight performance tests that won't overload CPU."""
import pytest
import time
from unittest.mock import patch, MagicMock
import sys
import os
from constants import TEST_MAX_CONCURRENT_AGENTS, TEST_TIMEOUT_SECONDS, TEST_MOCK_DELAY

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import discover_tools, clear_tools_cache
from orchestrator import TaskOrchestrator


@pytest.mark.slow  # Mark as slow for optional execution
def test_tool_discovery_performance_small_set():
    """Test tool discovery performance with small tool set."""
    # Given: Cleared cache
    clear_tools_cache()
    
    # When: Discovering tools multiple times
    times = []
    for i in range(3):
        start = time.time()
        tools = discover_tools({'performance': {'cache_tool_discovery': False}}, silent=True)
        times.append(time.time() - start)
    
    # Then: Discovery is reasonably fast
    avg_time = sum(times) / len(times)
    assert avg_time < 0.5, f"Tool discovery too slow: {avg_time:.3f}s average"
    assert len(tools) > 0  # Some tools found


def test_tool_discovery_cache_performance():
    """Test that cached tool discovery is significantly faster."""
    # Given: Config with caching enabled
    config = {'performance': {'cache_tool_discovery': True}}
    clear_tools_cache()
    
    # When: First discovery (cold)
    start1 = time.time()
    tools1 = discover_tools(config, silent=True)
    cold_time = time.time() - start1
    
    # And: Second discovery (cached)
    start2 = time.time()
    tools2 = discover_tools(config, silent=True)
    cached_time = time.time() - start2
    
    # Then: Cached is much faster
    assert cached_time < cold_time * 0.2, f"Cache not effective: {cached_time:.3f}s vs {cold_time:.3f}s"
    assert list(tools1.keys()) == list(tools2.keys())


def test_moderate_payload_handling(tmp_config):
    """Test handling of moderate-sized payloads (10KB)."""
    # Given: Moderate payload
    payload_size = 10 * 1024  # 10KB
    test_data = "x" * payload_size
    
    # Mock agent that returns the payload
    call_count = 0
    def mock_agent_factory(silent=False, **kwargs):
        nonlocal call_count
        agent = MagicMock()
        agent.tools = []
        agent.tool_mapping = {}
        
        # First call is for orchestrator, subsequent for actual work
        if call_count == 0:
            # Synthesis agent should return the large payload
            agent.run.return_value = test_data
        else:
            # Task agent also returns the payload
            agent.run.return_value = test_data
        
        call_count += 1
        return agent
    
    # When: Running orchestrator with single agent
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    
    # Override to use just 1 agent for this test
    orchestrator.num_agents = 1
    
    with patch.object(orchestrator, 'decompose_task') as mock_decompose:
        mock_decompose.return_value = ["Process this data"]
        
        start = time.time()
        result = orchestrator.orchestrate("Test")
        duration = time.time() - start
    
    # Then: Completes in reasonable time
    assert duration < 2.0, f"Processing took too long: {duration:.1f}s"
    assert len(result) >= payload_size


def test_prompt_size_limits(tmp_config):
    """Test that large prompts are handled efficiently."""
    # Given: Many mock tools
    with patch('tools.discover_tools') as mock_discover:
        tools = {}
        for i in range(50):  # Many tools but not excessive
            tool = MagicMock()
            tool.description = f"Tool {i} does something useful"
            tool.execute = MagicMock()
            tools[f'tool_{i}'] = tool
        mock_discover.return_value = tools
        
        # When: Creating agent (which builds prompt)
        from claude_code_cli_provider import ClaudeCodeCLIAgent
        
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            
            start = time.time()
            agent = ClaudeCodeCLIAgent(tmp_config, silent=True)
            duration = time.time() - start
        
        # Then: Prompt building is fast
        assert duration < 0.5, f"Prompt building too slow: {duration:.2f}s"
        assert len(agent.system_prompt) > 0


def test_memory_allocations_tracked():
    """Track memory allocations without stress testing."""
    import gc
    
    # Force garbage collection
    gc.collect()
    initial_objects = len(gc.get_objects())
    
    # Create and destroy some tools
    for _ in range(5):
        tools = discover_tools({'performance': {'cache_tool_discovery': False}}, silent=True)
        del tools
    
    # Force collection again
    gc.collect()
    final_objects = len(gc.get_objects())
    
    # Should not leak too many objects (adjusted for realistic growth)
    object_growth = final_objects - initial_objects
    # Allow for some growth due to imports and caching
    assert object_growth < 10000, f"Too many objects retained: {object_growth}"


@pytest.mark.slow
def test_timeout_handling_lightweight():
    """Test timeout handling with short operations."""
    # Given: Mock agent that sleeps briefly
    def slow_agent_factory(silent=False, **kwargs):
        agent = MagicMock()
        
        def mock_run(prompt):
            time.sleep(0.2)  # Brief delay
            return "Completed"
        
        agent.run.side_effect = mock_run
        agent.tools = []
        agent.tool_mapping = {}
        return agent
    
    # When: Running with very short timeout
    from concurrent.futures import TimeoutError
    
    config = {
        'provider': 'openrouter',
        'openrouter': {
            'api_key': 'test_key',
            'model': 'test_model'
        },
        'orchestrator': {
            'parallel_agents': 1,
            'task_timeout': 0.1,  # Very short timeout
            'aggregation_strategy': 'consensus',
            'question_generation_prompt': 'Generate {num_agents} questions for: {user_input}',
            'synthesis_prompt': 'Synthesize these responses: {agent_responses}'
        }
    }
    
    with open('test_config.yaml', 'w') as f:
        import yaml
        yaml.dump(config, f)
    
    try:
        orchestrator = TaskOrchestrator('test_config.yaml', silent=True, agent_factory=slow_agent_factory)
        
        # This should handle timeout gracefully
        result = orchestrator.orchestrate("Test")
        
        # Should get some result even with timeout
        assert result is not None
    finally:
        os.remove('test_config.yaml')