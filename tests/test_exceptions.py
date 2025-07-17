"""Tests for custom exception hierarchy."""
import pytest
from exceptions import (
    MakeItHeavyError,
    CLINotFoundError,
    ToolExecutionError,
    ToolNotFoundError,
    StreamingParseError,
    OpenRouterError,
    AgentTimeoutError
)


def test_cli_not_found_error():
    """CLINotFoundError includes helpful installation message."""
    # Given: A CLI path
    cli_path = "/usr/local/bin/claude"
    
    # When: Creating the exception
    error = CLINotFoundError(cli_path)
    
    # Then: Message includes path and installation instructions
    assert cli_path in str(error)
    assert "npm install" in str(error)
    assert isinstance(error, MakeItHeavyError)


def test_tool_execution_error():
    """ToolExecutionError includes tool name and error details."""
    # Given: Tool name and error
    tool_name = "calculate"
    error_msg = "Division by zero"
    
    # When: Creating the exception
    error = ToolExecutionError(tool_name, error_msg)
    
    # Then: Message includes both details
    assert tool_name in str(error)
    assert error_msg in str(error)
    assert error.tool_name == tool_name
    assert error.error == error_msg


def test_tool_not_found_error():
    """ToolNotFoundError includes the missing tool name."""
    # Given: A non-existent tool
    tool_name = "nonexistent_tool"
    
    # When: Creating the exception
    error = ToolNotFoundError(tool_name)
    
    # Then: Message includes tool name
    assert tool_name in str(error)
    assert error.tool_name == tool_name


def test_openrouter_error_with_status():
    """OpenRouterError handles status codes properly."""
    # Given: HTTP error details
    status_code = 500
    message = "Internal server error"
    
    # When: Creating with status code
    error = OpenRouterError(status_code=status_code, message=message)
    
    # Then: Message includes both
    assert "500" in str(error)
    assert message in str(error)
    assert error.status_code == status_code


def test_openrouter_error_without_status():
    """OpenRouterError works without status code."""
    # Given: Just an error message
    message = "Network timeout"
    
    # When: Creating without status code
    error = OpenRouterError(message=message)
    
    # Then: Message is preserved
    assert message in str(error)
    assert error.status_code is None


def test_agent_timeout_error():
    """AgentTimeoutError includes agent ID and timeout."""
    # Given: Agent details
    agent_id = 2
    timeout = 300
    
    # When: Creating the exception
    error = AgentTimeoutError(agent_id, timeout)
    
    # Then: Message includes details
    assert str(agent_id) in str(error)
    assert str(timeout) in str(error)
    assert error.agent_id == agent_id
    assert error.timeout == timeout


def test_exception_hierarchy():
    """All exceptions inherit from MakeItHeavyError."""
    # Given: Various exceptions
    exceptions = [
        CLINotFoundError("/path"),
        ToolExecutionError("tool", "error"),
        ToolNotFoundError("tool"),
        StreamingParseError("line", "error"),
        OpenRouterError(message="error"),
        AgentTimeoutError(1, 60)
    ]
    
    # Then: All are MakeItHeavyError instances
    for exc in exceptions:
        assert isinstance(exc, MakeItHeavyError)
        assert isinstance(exc, Exception)