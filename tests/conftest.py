import pytest
import yaml
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


@pytest.fixture
def tmp_config(tmp_path):
    """Creates a temporary config file with test defaults."""
    config_data = {
        "provider": "openrouter",
        "openrouter": {
            "api_key": "test-key-12345",
            "model": "mistralai/mistral-7b-instruct",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "claude_code": {
            "model": "claude-3",
            "max_turns": 10,
            "permission_mode": "auto",
            "allowed_tools": ["Bash(python use_tool.py *)"],
        },
        "system_prompt": "You are a helpful assistant. Use tools when appropriate.",
        "agent": {"max_iterations": 5, "iteration_delay": 0},
        "orchestrator": {
            "parallel_agents": 2,
            "task_timeout": 30,
            "aggregation_strategy": "ai_synthesis",
            "question_generation_prompt": "Generate {num_agents} focused questions for: {user_input}",
            "synthesis_prompt": "Synthesize these responses: {responses}",
        },
        "tools": {"search_web": {"max_results": 3}},
    }

    config_path = tmp_path / "test_config.yaml"
    with open(config_path, "w") as f:
        yaml.dump(config_data, f)

    return str(config_path)


@pytest.fixture
def clean_env(monkeypatch):
    """Cleans environment variables that might leak between tests."""
    env_vars_to_clean = [
        "OPENROUTER_API_KEY",
        "CLAUDE_API_KEY",
        "MOCK_MODE",
        "TEST_MODE",
    ]

    for var in env_vars_to_clean:
        monkeypatch.delenv(var, raising=False)

    yield


@pytest.fixture(autouse=True)
def clean_work_dir(tmp_path, monkeypatch):
    """Automatically changes to a clean working directory for each test."""
    original_cwd = os.getcwd()
    test_dir = tmp_path / "test_workspace"
    test_dir.mkdir()

    monkeypatch.chdir(test_dir)

    yield test_dir

    os.chdir(original_cwd)


@pytest.fixture
def orchestrator_fixture(tmp_config, mock_openai_client, monkeypatch):
    """
    Returns a fully wired TaskOrchestrator instance for integration tests.
    Re-uses tmp_config so each test gets isolated YAML.
    """
    from orchestrator import TaskOrchestrator  # local import to avoid circulars
    from agent import create_agent

    # Patch create_agent to use our mock client
    original_create_agent = create_agent

    def patched_create_agent(*args, **kwargs):
        kwargs["client"] = mock_openai_client
        return original_create_agent(*args, **kwargs)

    monkeypatch.setattr("orchestrator.create_agent", patched_create_agent)

    return TaskOrchestrator(config_path=tmp_config)


@pytest.fixture
def mock_openai_response():
    """Factory for creating mock OpenAI API responses."""

    def _create_response(content=None, tool_calls=None, finish_reason="stop"):
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls or []

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = finish_reason

        response = MagicMock()
        response.choices = [choice]

        return response

    return _create_response


@pytest.fixture
def mock_openai_client():
    """Mock OpenAI client that returns deterministic responses."""
    from tests.mocks.openai import MockOpenAIClient

    return MockOpenAIClient()


@pytest.fixture
def dummy_openrouter_key(monkeypatch):
    """Injects a dummy OpenRouter API key to avoid real API calls."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-dummy-key-12345")
    return "sk-test-dummy-key-12345"


@pytest.fixture
def base_config_dict():
    """Returns a base configuration dictionary for tests."""
    return {
        "provider": "openrouter",
        "openrouter": {
            "api_key": "test-key",
            "model": "test-model",
            "base_url": "https://openrouter.ai/api/v1",
        },
        "system_prompt": "Test assistant",
        "agent": {"max_iterations": 3},
    }


@pytest.fixture
def mock_tool_response():
    """Factory for creating mock tool responses."""

    def _create_response(tool_name, result=None, error=None):
        if error:
            return {"error": error}

        responses = {
            "calculate": {"result": result or 42},
            "search_web": {"results": result or ["Result 1", "Result 2"]},
            "read_file": {"content": result or "File content"},
            "write_file": {"success": True, "path": result or "test.txt"},
            "mark_task_complete": {"completed": True, "summary": result or "Task done"},
        }

        return responses.get(tool_name, {"result": result})

    return _create_response


@pytest.fixture
def isolated_tools_dir(tmp_path):
    """Creates an isolated tools directory for testing tool discovery."""
    tools_dir = tmp_path / "test_tools"
    tools_dir.mkdir()

    # Create __init__.py
    init_file = tools_dir / "__init__.py"
    init_file.write_text("""
from .base_tool import BaseTool

def discover_tools(config, silent=True):
    return {}
""")

    # Create base_tool.py
    base_tool = tools_dir / "base_tool.py"
    base_tool.write_text("""
class BaseTool:
    def __init__(self, config):
        self.config = config
    
    @property
    def name(self):
        raise NotImplementedError
    
    @property
    def description(self):
        raise NotImplementedError
    
    @property
    def parameters(self):
        raise NotImplementedError
    
    def execute(self, **kwargs):
        raise NotImplementedError
""")

    return tools_dir
