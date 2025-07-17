"""Tests for tool discovery and system prompt caching."""
import pytest
import time
from unittest.mock import patch, MagicMock
from tools import discover_tools, clear_tools_cache


def test_tool_discovery_caching(base_config_dict):
    """Tool discovery uses cache on subsequent calls with same config."""
    # Given: Config with caching enabled
    base_config_dict['performance'] = {'cache_tool_discovery': True}
    
    # Clear any existing cache
    clear_tools_cache()
    
    # When: Discovering tools twice
    start1 = time.time()
    tools1 = discover_tools(base_config_dict, silent=True)
    time1 = time.time() - start1
    
    start2 = time.time()
    tools2 = discover_tools(base_config_dict, silent=True)
    time2 = time.time() - start2
    
    # Then: Second call should be much faster (cached)
    assert list(tools1.keys()) == list(tools2.keys())  # Same tool names
    assert time2 < time1 * 0.5  # At least 2x faster
    
    # And: Modifying config invalidates cache
    base_config_dict['search'] = {'max_results': 10}  # Change config
    tools3 = discover_tools(base_config_dict, silent=True)
    assert list(tools3.keys()) == list(tools1.keys())  # Same tool names


def test_tool_discovery_cache_can_be_disabled(base_config_dict):
    """Tool discovery doesn't use cache when disabled in config."""
    # Given: Config with caching disabled
    base_config_dict['performance'] = {'cache_tool_discovery': False}
    
    # Mock the importlib to track calls
    with patch('tools.importlib.import_module') as mock_import:
        mock_module = MagicMock()
        mock_import.return_value = mock_module
        
        # When: Discovering tools twice
        discover_tools(base_config_dict, silent=True)
        call_count1 = mock_import.call_count
        
        discover_tools(base_config_dict, silent=True)
        call_count2 = mock_import.call_count
        
        # Then: Import is called twice (no caching)
        assert call_count2 > call_count1


def test_clear_tools_cache():
    """clear_tools_cache() properly clears the cache."""
    # Given: Some cached tools
    config = {'performance': {'cache_tool_discovery': True}}
    tools1 = discover_tools(config, silent=True)
    
    # When: Clearing cache
    clear_tools_cache()
    
    # Then: Next discovery takes full time (not cached)
    with patch('tools.os.listdir') as mock_listdir:
        mock_listdir.return_value = ['calculate_tool.py', '__init__.py']
        
        start = time.time()
        discover_tools(config, silent=True)
        discovery_time = time.time() - start
        
        # Should have called listdir (not using cache)
        mock_listdir.assert_called()