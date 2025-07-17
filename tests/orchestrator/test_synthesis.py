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
    # Given: Mock agent factory that returns synthesis response
    def mock_agent_factory(silent=False, **kwargs):
        mock_agent = MagicMock()
        mock_agent.run.return_value = "Based on the analysis, 2+2 equals 4 mathematically, and this has been fundamental throughout history."
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        return mock_agent

    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)

    # When: Aggregating multiple responses
    agent_results = [
        {"agent_id": 0, "status": "success", "response": "From a mathematical perspective, 2+2=4.", "execution_time": 1.0},
        {"agent_id": 1, "status": "success", "response": "Historically, basic arithmetic has been crucial for trade.", "execution_time": 1.0},
    ]

    result = orchestrator.aggregate_results(agent_results)

    # Then: Returns combined synthesis
    assert result is not None
    assert isinstance(result, str)
    assert len(result) > 0


def test_synthesis_handles_empty_responses_gracefully(tmp_config, clean_env):
    """Synthesizer handles case when all agents fail."""
    # Mock agent factory not needed for this test
    orchestrator = TaskOrchestrator(tmp_config, silent=True)

    # When: No successful results to aggregate
    agent_results = []  # Empty results
    result = orchestrator.aggregate_results(agent_results)

    # Then: Returns meaningful message
    assert result is not None
    assert "failed" in result.lower() or "all agents" in result.lower()


def test_synthesis_preserves_key_information(tmp_config, clean_env):
    """Synthesis preserves important information from agent responses."""
    # Given: Mock agent factory that synthesizes based on input
    def mock_agent_factory(silent=False, **kwargs):
        mock_agent = MagicMock()
        
        def synthesis_response(prompt):
            if "quantum" in prompt and "classical" in prompt:
                return "Both quantum mechanics and classical physics perspectives are important."
            else:
                return "Synthesized response based on agent inputs."
        
        mock_agent.run.side_effect = synthesis_response
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        return mock_agent

    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)

    # When: Aggregating responses with key terms
    agent_results = [
        {"agent_id": 0, "status": "success", "response": "From quantum mechanics perspective...", "execution_time": 1.0},
        {"agent_id": 1, "status": "success", "response": "In classical physics...", "execution_time": 1.0},
    ]

    result = orchestrator.aggregate_results(agent_results)

    # Then: Synthesis mentions both perspectives
    assert "quantum" in result.lower()
    assert "classical" in result.lower()


def test_synthesis_handles_conflicting_responses(tmp_config, clean_env):
    """Synthesizer reconciles conflicting information from agents."""
    # Given: Mock agent factory for synthesis
    def mock_agent_factory(silent=False, **kwargs):
        mock_agent = MagicMock()
        mock_agent.run.return_value = "While there are different perspectives, the consensus is that proper testing is essential."
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        return mock_agent

    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)

    # When: Agents disagree
    agent_results = [
        {"agent_id": 0, "status": "success", "response": "Testing is absolutely critical and should be done first.", "execution_time": 1.0},
        {"agent_id": 1, "status": "success", "response": "Testing can be done after implementation.", "execution_time": 1.0},
        {"agent_id": 2, "status": "success", "response": "Testing should be continuous throughout.", "execution_time": 1.0},
    ]

    result = orchestrator.aggregate_results(agent_results)

    # Then: Synthesis acknowledges different views
    assert "perspectives" in result or "consensus" in result


def test_synthesis_api_failure_returns_fallback(tmp_config, clean_env):
    """When synthesis API fails, returns concatenated responses as fallback."""
    # Given: Mock agent factory that fails during synthesis
    def mock_agent_factory(silent=False, **kwargs):
        mock_agent = MagicMock()
        mock_agent.run.side_effect = Exception("API Error")
        mock_agent.tools = []
        mock_agent.tool_mapping = {}
        return mock_agent

    orchestrator = TaskOrchestrator(tmp_config, silent=True, agent_factory=mock_agent_factory)

    # When: Synthesis fails
    agent_results = [
        {"agent_id": 0, "status": "success", "response": "Response 1", "execution_time": 1.0},
        {"agent_id": 1, "status": "success", "response": "Response 2", "execution_time": 1.0},
    ]
    result = orchestrator.aggregate_results(agent_results)

    # Then: Returns fallback combination
    assert result is not None
    assert "Response 1" in result or "Response 2" in result
