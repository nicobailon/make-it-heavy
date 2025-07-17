"""
Custom exception hierarchy for Make It Heavy framework.

This module defines custom exceptions used throughout the application
for better error handling and debugging.
"""


class MakeItHeavyError(Exception):
    """Base exception for all Make It Heavy errors."""
    pass


class ClaudeCodeError(MakeItHeavyError):
    """Base exception for Claude Code CLI related errors."""
    pass


class CLINotFoundError(ClaudeCodeError):
    """Raised when Claude Code CLI is not installed or not found in PATH."""
    
    def __init__(self, cli_path: str):
        self.cli_path = cli_path
        super().__init__(
            f"Claude CLI not found at '{cli_path}'. "
            "Please install with: npm install -g @anthropic-ai/claude-code"
        )


class CLIVerificationError(ClaudeCodeError):
    """Raised when Claude Code CLI verification fails."""
    pass


class ToolError(MakeItHeavyError):
    """Base exception for tool-related errors."""
    pass


class ToolExecutionError(ToolError):
    """Raised when a tool execution fails."""
    
    def __init__(self, tool_name: str, error: str):
        self.tool_name = tool_name
        self.error = error
        super().__init__(f"Tool '{tool_name}' execution failed: {error}")


class ToolNotFoundError(ToolError):
    """Raised when a requested tool is not found."""
    
    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in available tools")


class StreamingParseError(ClaudeCodeError):
    """Raised when parsing streaming JSON from Claude Code CLI fails."""
    
    def __init__(self, line: str, error: str):
        self.line = line
        self.parse_error = error
        super().__init__(f"Failed to parse JSON line: {error}")


class ConfigurationError(MakeItHeavyError):
    """Raised when there's an issue with configuration."""
    pass


class ProviderError(MakeItHeavyError):
    """Base exception for provider-related errors."""
    pass


class OpenRouterError(ProviderError):
    """Raised when OpenRouter API calls fail."""
    
    def __init__(self, status_code: int = None, message: str = None):
        self.status_code = status_code
        if status_code:
            super().__init__(f"OpenRouter API error {status_code}: {message}")
        else:
            super().__init__(f"OpenRouter API error: {message}")


class OrchestrationError(MakeItHeavyError):
    """Raised when orchestration fails."""
    pass


class AgentTimeoutError(OrchestrationError):
    """Raised when an agent times out during orchestration."""
    
    def __init__(self, agent_id: int, timeout: int):
        self.agent_id = agent_id
        self.timeout = timeout
        super().__init__(f"Agent {agent_id} timed out after {timeout} seconds")