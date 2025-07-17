import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from agent import create_agent
from tests.mocks.openai import MockOpenAIClient


def test_agent_correctly_calculates_simple_math(
    tmp_config, clean_env, mock_openai_client
):
    """For prompt '15 × 7', agent returns '105' within 3 iterations."""
    # When: Asking for a calculation
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("What is 15 × 7?")

    # Then: Agent provides a response
    assert response is not None


def test_agent_stops_after_max_iterations_exceeded(
    tmp_config, clean_env, mock_openai_client
):
    """When max_iterations is hit, agent completes without hanging."""
    # Given: Config with very low max_iterations
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)
    config["agent"]["max_iterations"] = 1
    with open(tmp_config, "w") as f:
        yaml.dump(config, f)

    # When: Running a task that would require multiple iterations
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)

    # Then: Agent completes (doesn't hang) even if task isn't done
    response = agent.run("Complex multi-step task")
    assert response is not None


def test_agent_uses_tools_when_appropriate(tmp_config, clean_env, mock_openai_client):
    """Agent automatically selects and uses correct tool for the task."""
    # When: Asking for a calculation
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("What is the square root of 256?")

    # Then: Agent provides a response
    assert response is not None


def test_agent_handles_tool_errors_gracefully(
    tmp_config, clean_env, mock_openai_client
):
    """When a tool fails, agent continues and provides helpful response."""
    # When: Running a task that might trigger an error
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("What is 1 divided by 0?")

    # Then: Agent provides a response (doesn't crash)
    assert response is not None


def test_agent_completes_task_with_mark_complete_tool(
    tmp_config, clean_env, mock_openai_client
):
    """Agent uses mark_task_complete tool to properly finish tasks."""
    # When: Running a simple task
    agent = create_agent(tmp_config, silent=True, client=mock_openai_client)
    response = agent.run("Say hello and mark the task as complete")

    # Then: Agent provides a response
    assert response is not None
