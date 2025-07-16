import pytest
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tools import discover_tools


def test_discover_tools_returns_expected_tool_set(base_config_dict):
    """discover_tools returns the expected set of tools."""
    # When: Discovering tools
    tools = discover_tools(base_config_dict, silent=True)

    # Then: Core tools are present
    expected_tools = {
        "calculate",
        "search_web",
        "read_file",
        "write_file",
        "mark_task_complete",
    }
    actual_tools = set(tools.keys())

    # At least the core tools should be present
    assert expected_tools.issubset(actual_tools), (
        f"Missing tools: {expected_tools - actual_tools}"
    )


def test_discovered_tools_are_callable(base_config_dict):
    """All discovered tools can be executed without crashing."""
    # Given: Discovered tools
    tools = discover_tools(base_config_dict, silent=True)

    # When/Then: Each tool can be called with appropriate parameters
    test_params = {
        "calculate": {"expression": "1+1"},
        "search_web": {"query": "test"},
        "read_file": {"path": "nonexistent.txt"},  # Should handle gracefully
        "write_file": {"path": "test.txt", "content": "test"},
        "mark_task_complete": {"task_summary": "test", "completion_message": "done"},
    }

    for tool_name, params in test_params.items():
        if tool_name in tools:
            # Tool should be executable without crashing
            try:
                result = tools[tool_name].execute(**params)
                assert isinstance(result, dict), f"{tool_name} should return a dict"
            except FileNotFoundError:
                # Expected for read_file with nonexistent file
                pass
            except Exception as e:
                # Network errors are acceptable for search_web
                if tool_name == "search_web" and "network" in str(e).lower():
                    pass
                else:
                    pytest.fail(f"Tool {tool_name} crashed unexpectedly: {e}")


def test_tools_handle_missing_required_parameters(base_config_dict):
    """Tools provide helpful error messages for missing parameters."""
    # Given: Discovered tools
    tools = discover_tools(base_config_dict, silent=True)

    # When: Calling tools without required parameters
    if "calculate" in tools:
        with pytest.raises(TypeError) as exc_info:
            tools["calculate"].execute()  # Missing 'expression'

        # Then: Error mentions the missing parameter
        assert (
            "expression" in str(exc_info.value)
            or "required" in str(exc_info.value).lower()
        )


def test_tool_discovery_handles_empty_config(clean_env):
    """Tool discovery works even with minimal config."""
    # Given: Minimal config
    minimal_config = {}

    # When: Discovering tools
    tools = discover_tools(minimal_config, silent=True)

    # Then: At least some tools are discovered
    assert len(tools) > 0, "Should discover at least some tools with empty config"
