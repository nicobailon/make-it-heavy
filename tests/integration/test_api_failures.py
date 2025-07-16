import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from agent import create_agent
from orchestrator import TaskOrchestrator


def test_agent_handles_openrouter_500_error_gracefully(tmp_config, clean_env):
    """When OpenRouter returns 500, agent provides graceful error message."""
    # Given: OpenAI client that simulates 500 error
    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Server error: 500")
        mock_openai_class.return_value = mock_client

        # When: Creating agent and running task
        agent = create_agent(tmp_config, silent=True)
        result = agent.run("Calculate 2+2")

        # Then: Agent handles error gracefully
        assert result is not None
        assert "error" in str(result).lower() or "failed" in str(result).lower()


def test_agent_retries_on_transient_network_errors(tmp_config, clean_env):
    """Agent retries on network errors before giving up."""
    # Given: Client that fails then succeeds
    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()

        # First call fails, second succeeds
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="The answer is 4"))
        ]

        mock_client.chat.completions.create.side_effect = [
            Exception("Network error"),
            mock_response,
        ]
        mock_openai_class.return_value = mock_client

        # When: Running task
        agent = create_agent(tmp_config, silent=True)
        result = agent.run("What is 2+2?")

        # Then: Eventually succeeds
        assert "4" in str(result)


def test_orchestrator_continues_when_agent_creation_fails(tmp_config, clean_env):
    """Orchestrator continues with remaining agents when one fails to create."""
    # Given: Agent creation that sometimes fails
    create_count = 0

    def mock_create_agent(config, silent):
        nonlocal create_count
        create_count += 1
        if create_count == 2:
            raise RuntimeError("Failed to create agent")

        mock_agent = MagicMock()
        mock_agent.run.return_value = f"Response from agent {create_count}"
        return mock_agent

    with patch("orchestrator.create_agent", side_effect=mock_create_agent):
        with patch("orchestrator.OpenAI") as mock_openai:
            mock_client = MagicMock()
            # Mock decomposition
            mock_client.chat.completions.create.return_value = MagicMock(
                choices=[MagicMock(message=MagicMock(content="1. Q1\n2. Q2\n3. Q3"))]
            )
            mock_openai.return_value = mock_client

            # When: Running orchestration
            orchestrator = TaskOrchestrator(tmp_config, silent=True)
            with patch.object(orchestrator, "synthesize_responses") as mock_synth:
                mock_synth.return_value = "Combined response"

                result = orchestrator.orchestrate("Test task")

                # Then: Completes with available agents
                assert result is not None
                # Should have responses from agents 1 and 3 (2 failed)
                responses = mock_synth.call_args[0][0]
                assert len(responses) == 2


def test_tool_errors_dont_crash_agent(tmp_config, clean_env):
    """When tools throw exceptions, agent continues gracefully."""
    # Given: Tools that fail
    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()

        # Agent tries tool, then provides alternative response
        tool_response = MagicMock()
        tool_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=None,
                    tool_calls=[
                        MagicMock(
                            id="call_123",
                            function=MagicMock(
                                name="calculate", arguments='{"expression": "1/0"}'
                            ),
                        )
                    ],
                )
            )
        ]

        fallback_response = MagicMock()
        fallback_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="I encountered an error, but division by zero is undefined."
                )
            )
        ]

        mock_client.chat.completions.create.side_effect = [
            tool_response,
            fallback_response,
        ]
        mock_openai_class.return_value = mock_client

        # Mock tools that fail
        with patch("tools.discover_tools") as mock_discover:
            mock_calc = MagicMock()
            mock_calc.execute.side_effect = ZeroDivisionError("Cannot divide by zero")
            mock_discover.return_value = {"calculate": mock_calc}

            # When: Running task that triggers tool error
            agent = create_agent(tmp_config, silent=True)
            result = agent.run("What is 1/0?")

            # Then: Agent provides helpful response
            assert result is not None
            assert "error" in str(result).lower() or "undefined" in str(result).lower()


def test_api_timeout_handled_gracefully(tmp_config, clean_env):
    """API timeouts are handled with appropriate error messages."""
    # Given: API that times out
    import time

    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()

        def slow_api_call(**kwargs):
            time.sleep(0.1)  # Simulate slow response
            raise Exception("Request timeout")

        mock_client.chat.completions.create.side_effect = slow_api_call
        mock_openai_class.return_value = mock_client

        # When: Making request
        agent = create_agent(tmp_config, silent=True)
        result = agent.run("Quick question")

        # Then: Timeout is handled
        assert result is not None
        assert "timeout" in str(result).lower() or "error" in str(result).lower()


def test_malformed_api_response_handled(tmp_config, clean_env):
    """Malformed API responses don't crash the system."""
    # Given: API returning malformed response
    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()

        # Create response missing expected fields
        bad_response = MagicMock()
        bad_response.choices = []  # No choices

        mock_client.chat.completions.create.return_value = bad_response
        mock_openai_class.return_value = mock_client

        # When: Running task
        agent = create_agent(tmp_config, silent=True)
        result = agent.run("Test")

        # Then: Handles gracefully
        assert result is not None  # Doesn't crash
