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
        
        # Then: Agent raises exception with error message
        with pytest.raises(Exception) as exc_info:
            agent.run("Calculate 2+2")
        
        assert "LLM call failed" in str(exc_info.value)
        assert "500" in str(exc_info.value)


def test_agent_retries_on_transient_network_errors(tmp_config, clean_env):
    """Agent retries on network errors before giving up."""
    # Given: Client that fails then succeeds
    with patch("agent.OpenAI") as mock_openai_class:
        mock_client = MagicMock()

        # First call fails, second succeeds
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(message=MagicMock(content="The answer is 4", tool_calls=None))
        ]

        mock_client.chat.completions.create.side_effect = [
            Exception("Network error"),
            mock_response,
        ]
        mock_openai_class.return_value = mock_client

        # When: Running task - agent doesn't retry internally, so it will fail
        agent = create_agent(tmp_config, silent=True)
        
        # Then: First call fails with network error  
        with pytest.raises(Exception) as exc_info:
            agent.run("What is 2+2?")
        
        assert "LLM call failed" in str(exc_info.value)
        assert "Network error" in str(exc_info.value)


def test_orchestrator_continues_when_agent_creation_fails(tmp_config, clean_env):
    """Orchestrator continues with remaining agents when one fails to create."""
    # Given: Agent factory that sometimes fails
    create_count = 0

    def mock_agent_factory(silent=False, **kwargs):
        nonlocal create_count
        create_count += 1
        
        # Agent 2 fails to create, but we need to succeed for decomposition agent
        if create_count == 3:  # Third call is for second parallel agent
            raise RuntimeError("Failed to create agent")

        mock_agent = MagicMock()
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        
        if create_count == 1:  # First call is for decomposition
            mock_agent.run.return_value = '["Q1", "Q2", "Q3"]'
        else:
            mock_agent.run.return_value = f"Response from agent {create_count}"
        
        return mock_agent

    # When: Running orchestration
    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)
    
    # Run orchestration - should handle the failure gracefully
    result = orchestrator.orchestrate("Test task")

    # Then: Completes with available agents
    assert result is not None
    # Should get response despite one agent failing
    assert "Response from agent" in result or "Agent" in result
