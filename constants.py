"""
Constants for Make It Heavy framework.

This module contains non-configurable constants used throughout the application.
For configurable values, see config.yaml.
"""

# Display limits for debugging and output formatting
DEFAULT_PREVIEW_LINES = 10
DEFAULT_PREVIEW_DISPLAY_LINES = 5
DEFAULT_LINE_TRUNCATE_LENGTH = 80
DEFAULT_JSON_PREVIEW_LENGTH = 50

# Timeout defaults (in seconds)
DEFAULT_CLI_VERIFICATION_TIMEOUT = 5
DEFAULT_PROGRESS_UPDATE_INTERVAL = 5

# Threading and concurrency
DEFAULT_MAX_WORKERS = 4
DEFAULT_TASK_TIMEOUT = 300

# Prompt size limits
DEFAULT_MAX_PROMPT_SIZE = 10000  # characters
DEFAULT_TOOL_EXAMPLE_TRUNCATE = 500  # characters per tool example

# Tool discovery
TOOL_FILE_EXCLUDES = ["__init__.py", "base_tool.py"]

# File operations
DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
DEFAULT_ENCODING = "utf-8"

# XML parsing safety limits
MAX_XML_SIZE = 10000  # bytes
MAX_XML_DEPTH = 5

# Testing constants (CPU-friendly limits)
TEST_MAX_CONCURRENT_AGENTS = 3
TEST_TIMEOUT_SECONDS = 5
TEST_MOCK_DELAY = 0.1