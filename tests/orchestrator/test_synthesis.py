import pytest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from orchestrator import TaskOrchestrator


def test_synthesizer_combines_multiple_agent_responses(tmp_config, clean_env):
    """Given 2 mock agent answers, synthesizer returns combined paragraph."""
    # Given: Orchestrator with mock synthesis
    with patch("orchestrator.OpenAI") as mock_openai:
        mock_client = MagicMock()

        # Mock synthesis response
        synthesis_response = MagicMock()
        synthesis_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="Based on the analysis, 2+2 equals 4 mathematically, and this has been fundamental throughout history."
                )
            )
        ]
        mock_client.chat.completions.create.return_value = synthesis_response
        mock_openai.return_value = mock_client

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # When: Synthesizing multiple responses
        agent_responses = [
            "From a mathematical perspective, 2+2=4.",
            "Historically, basic arithmetic has been crucial for trade.",
        ]

        result = orchestrator.synthesize_responses(agent_responses)

        # Then: Returns combined synthesis
        assert result is not None
        assert isinstance(result, str)
        assert len(result) > 0


def test_synthesis_handles_empty_responses_gracefully(tmp_config, clean_env):
    """Synthesizer handles case when all agents fail."""
    orchestrator = TaskOrchestrator(tmp_config, silent=True)

    # When: No responses to synthesize
    result = orchestrator.synthesize_responses([])

    # Then: Returns meaningful message
    assert result is not None
    assert "no responses" in result.lower() or "failed" in result.lower()


def test_synthesis_preserves_key_information(tmp_config, clean_env):
    """Synthesis preserves important information from agent responses."""
    # Given: Mock synthesis that includes key facts
    with patch("orchestrator.OpenAI") as mock_openai:
        mock_client = MagicMock()

        def create_synthesis_response(**kwargs):
            messages = kwargs.get("messages", [])
            # Extract the responses from the prompt
            user_msg = messages[-1]["content"] if messages else ""

            if "quantum" in user_msg and "classical" in user_msg:
                content = "Both quantum mechanics and classical physics perspectives are important."
            else:
                content = "Synthesized response based on agent inputs."

            response = MagicMock()
            response.choices = [MagicMock(message=MagicMock(content=content))]
            return response

        mock_client.chat.completions.create.side_effect = create_synthesis_response
        mock_openai.return_value = mock_client

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # When: Synthesizing responses with key terms
        responses = ["From quantum mechanics perspective...", "In classical physics..."]

        result = orchestrator.synthesize_responses(responses)

        # Then: Synthesis mentions both perspectives
        assert "quantum" in result.lower()
        assert "classical" in result.lower()


def test_synthesis_handles_conflicting_responses(tmp_config, clean_env):
    """Synthesizer reconciles conflicting information from agents."""
    # Given: Conflicting responses
    with patch("orchestrator.OpenAI") as mock_openai:
        mock_client = MagicMock()

        synthesis_response = MagicMock()
        synthesis_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="While there are different perspectives, the consensus is that proper testing is essential."
                )
            )
        ]
        mock_client.chat.completions.create.return_value = synthesis_response
        mock_openai.return_value = mock_client

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # When: Agents disagree
        responses = [
            "Testing is absolutely critical and should be done first.",
            "Testing can be done after implementation.",
            "Testing should be continuous throughout.",
        ]

        result = orchestrator.synthesize_responses(responses)

        # Then: Synthesis acknowledges different views
        assert "perspectives" in result or "consensus" in result


def test_synthesis_api_failure_returns_fallback(tmp_config, clean_env):
    """When synthesis API fails, returns concatenated responses as fallback."""
    # Given: API that will fail
    with patch("orchestrator.OpenAI") as mock_openai:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        orchestrator = TaskOrchestrator(tmp_config, silent=True)

        # When: Synthesis fails
        responses = ["Response 1", "Response 2"]
        result = orchestrator.synthesize_responses(responses)

        # Then: Returns fallback combination
        assert result is not None
        assert "Response 1" in result or "Response 2" in result
