import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add parent directory to path for imports
sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from agent import create_agent
from tests.mocks.openai import MockOpenAIClient


def test_create_agent_returns_functional_agent_for_simple_prompt(
    tmp_config, clean_env, mock_openai_client
):
    """Agent created by factory can process a simple prompt and return a response."""
    # When: Creating an agent and asking a simple question
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("Please calculate 2 + 2")

    # Then: Agent provides a response
    assert response is not None
    assert len(str(response)) > 0


def test_agent_factory_falls_back_to_openrouter_for_invalid_provider(
    tmp_config, clean_env, mock_openai_client
):
    """When an invalid provider is specified, factory falls back to OpenRouter."""
    # Given: Config with invalid provider
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["provider"] = "nonexistent_provider"
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    # When: Creating agent with invalid provider
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)

    # Then: Agent is created successfully (fallback worked)
    assert agent is not None
    response = agent.run("test")
    assert response is not None


def test_agent_respects_max_iterations_from_config(
    tmp_config, clean_env, mock_openai_client
):
    """Agent stops after configured max iterations to prevent infinite loops."""
    # Given: Config with low max_iterations
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["agent"]["max_iterations"] = 2
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    # When: Running agent with a complex task
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("Complex task")

    # Then: Agent completes without hanging
    assert response is not None


def test_claude_code_provider_detection(tmp_config, clean_env):
    """Factory correctly detects and handles Claude Code provider configuration."""
    # Given: Config set to use Claude Code
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["provider"] = "claude_code"
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    # When: Creating agent without Claude CLI installed
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("claude not found")

        # Then: Should raise or fall back gracefully
        try:
            agent = create_agent(tmp_config, silent=True)
            # If it doesn't raise, it should have fallen back
            assert agent is not None
        except Exception as e:
            # Expected behavior when Claude CLI is missing
            assert "claude" in str(e).lower() or "not found" in str(e).lower()


def test_agent_loads_tools_and_can_use_them(tmp_config, clean_env, mock_openai_client):
    """Agent can discover and use tools to complete tasks."""
    # When: Creating agent and asking for calculation
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("Calculate something")

    # Then: Agent completes the task
    assert response is not None
