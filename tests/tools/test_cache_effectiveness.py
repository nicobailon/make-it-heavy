"""Tests to verify tool discovery cache effectiveness."""
import pytest
from unittest import mock
import time
import yaml
from tools import discover_tools, clear_tools_cache


def test_cache_not_invalidated_by_unrelated_config_changes():
    """Tool cache should not be invalidated by non-tool config changes."""
    # Given: Config with caching enabled
    config1 = {
        'performance': {'cache_tool_discovery': True},
        'search': {'max_results': 5},
        'agent': {'max_iterations': 10},
        'openrouter': {'api_key': 'test-key-1'}
    }
    
    # Clear any existing cache
    clear_tools_cache()
    
    # When: Discovering tools first time
    start1 = time.time()
    tools1 = discover_tools(config1, silent=True)
    initial_time = time.time() - start1
    
    # Create new config with only non-tool changes
    config2 = {
        'performance': {'cache_tool_discovery': True},
        'search': {'max_results': 5},  # Same as before
        'agent': {'max_iterations': 20},  # Changed!
        'openrouter': {'api_key': 'different-key'},  # Changed!
        'new_section': {'new_value': 123}  # Added!
    }
    
    # Discover again with modified config
    start2 = time.time()
    tools2 = discover_tools(config2, silent=True)
    cache_time = time.time() - start2
    
    # Then: Should use cache (much faster)
    assert cache_time < initial_time * 0.1, f"Cache time {cache_time:.3f}s >= initial {initial_time:.3f}s * 0.1"
    assert list(tools1.keys()) == list(tools2.keys())


def test_cache_invalidated_by_tool_config_changes():
    """Tool cache should be invalidated when tool-specific config changes."""
    # Given: Initial config
    config1 = {
        'performance': {'cache_tool_discovery': True},
        'search': {'max_results': 5}
    }
    
    # Clear cache and discover
    clear_tools_cache()
    tools1 = discover_tools(config1, silent=True)
    
    # When: Changing tool-specific config
    config2 = {
        'performance': {'cache_tool_discovery': True},
        'search': {'max_results': 10}  # Changed!
    }
    
    # Track if tools are re-instantiated
    import importlib
    with mock.patch.object(importlib, 'import_module') as mock_import:
        # Set up mock to return a module with tool classes
        mock_module = mock.MagicMock()
        mock_import.return_value = mock_module
        
        tools2 = discover_tools(config2, silent=True)
        
        # Then: Should have re-imported (cache invalidated)
        assert mock_import.called


def test_multiple_agents_share_cache():
    """Multiple agent instances should share the tool cache."""
    from claude_code_cli_provider import ClaudeCodeCLIAgent
    import subprocess
    
    # Clear cache first
    clear_tools_cache()
    
    # Mock config loading and subprocess
    mock_config = {
        'performance': {'cache_tool_discovery': True},
        'search': {'max_results': 5},
        'claude_code': {
            'model': 'claude-test',
            'max_turns': 20,
            'system_prompt': 'Test prompt'
        }
    }
    
    with mock.patch('subprocess.run') as mock_run:
        mock_run.return_value = mock.MagicMock(returncode=0)
        
        with mock.patch('builtins.open', mock.mock_open(read_data='')) as mock_file:
            with mock.patch('yaml.safe_load') as mock_yaml:
                mock_yaml.return_value = mock_config
                
                # Create first agent (cold cache)
                start1 = time.time()
                agent1 = ClaudeCodeCLIAgent(silent=True)
                time1 = time.time() - start1
                
                # Create second agent (should use cache)
                start2 = time.time()
                agent2 = ClaudeCodeCLIAgent(silent=True)
                time2 = time.time() - start2
                
                # Second should be much faster
                assert time2 < time1 * 0.5, f"Second agent ({time2:.3f}s) not faster than first ({time1:.3f}s)"
                
                # Both should have same tools
                assert list(agent1.discovered_tools.keys()) == list(agent2.discovered_tools.keys())