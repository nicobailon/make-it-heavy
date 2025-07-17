# Testing Strategy: Mocking vs Real API Calls

## The Testing Dilemma

When testing AI agent systems, we face a classic trade-off between test accuracy and practicality. This document outlines our approach to balancing these concerns.

## Current Approach Analysis

### Mocking (What We're Doing) - Pros:
1. **Cost-effective**: No API charges for running tests
2. **Fast**: Tests run in milliseconds vs seconds
3. **Reliable**: No network issues, rate limits, or API downtime
4. **CI-friendly**: Works in any environment without credentials
5. **Deterministic**: Same input = same output every time

### Mocking - Cons:
1. **Accuracy concerns**: Mocks might not reflect real API behavior
2. **API changes**: Won't catch breaking changes in OpenRouter/Claude APIs
3. **Edge cases**: Might miss real-world error scenarios
4. **False confidence**: Tests pass but real integration could fail

## Recommended Solution: Hybrid Testing Strategy

Based on behavior-focused testing principles from CLAUDE.md, we recommend a three-tier approach:

### 1. Unit Tests (Mocked) - Run Always
- Test business logic and behavior contracts
- Mock all external dependencies
- Run on every commit, PR, and in CI
- Focus on behavior, not implementation

**Example:**
```python
def test_agent_calculation_behavior(mock_openai):
    """Unit test with mocked API - tests behavior contract"""
    mock_openai.return_value.chat.completions.create.return_value = 
        realistic_calculation_response()
    
    agent = create_agent(config, client=mock_openai)
    result = agent.run("Calculate 2+2")
    assert "4" in result  # Verify behavior, not implementation
```

### 2. Integration Tests - Run Periodically
- Use real APIs with test/development keys
- Run less frequently (nightly, before releases)
- Test actual API integration points
- Use cheaper models for cost control

**Example:**
```python
# tests/integration/test_real_api.py
@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("RUN_INTEGRATION_TESTS"), reason="Expensive API tests")
def test_real_openrouter_calculation():
    """Integration test with real OpenRouter API"""
    config = load_test_config()  # Uses test API key, cheaper model
    agent = create_agent(config)
    result = agent.run("Calculate 2+2")
    assert "4" in result
```

### 3. Contract Tests - Optional but Valuable
- Record real API responses as fixtures
- Validate mocks match real API structure
- Update fixtures periodically
- Bridge between unit and integration tests

**Example:**
```python
# fixtures/openrouter_responses.py
REAL_CALCULATION_RESPONSE = {
    "choices": [{
        "message": {
            "content": "The answer is 4",
            "role": "assistant"
        },
        "finish_reason": "stop"
    }],
    "model": "anthropic/claude-3-sonnet",
    "usage": {"prompt_tokens": 50, "completion_tokens": 10}
}
```

## Implementation Guide

### 1. Test Organization
```
tests/
├── unit/              # Mocked tests (run in CI)
│   ├── test_agent_behavior.py
│   ├── test_orchestrator.py
│   └── test_tools.py
├── integration/       # Real API tests (run periodically)
│   ├── test_openrouter_api.py
│   ├── test_claude_code_api.py
│   └── test_end_to_end.py
└── fixtures/         # Recorded API responses
    ├── openrouter_responses.py
    └── error_responses.py
```

### 2. Configuration for Test Environments

```yaml
# config.test.yaml - For unit tests
provider: "openrouter"
openrouter:
  api_key: "mock-key"
  model: "mock-model"

# config.integration.yaml - For integration tests
provider: "openrouter"
openrouter:
  api_key: ${INTEGRATION_TEST_API_KEY}
  model: "openai/gpt-3.5-turbo"  # Cheaper for tests

# config.integration-claude.yaml
provider: "openrouter"  
openrouter:
  api_key: ${INTEGRATION_TEST_API_KEY}
  model: "anthropic/claude-3-haiku-20240307"  # Cheapest Claude
```

### 3. Running Different Test Suites

```bash
# Run unit tests only (for CI)
pytest tests/unit/

# Run integration tests (manually or nightly)
RUN_INTEGRATION_TESTS=1 pytest tests/integration/

# Run all tests
RUN_INTEGRATION_TESTS=1 pytest

# Run with coverage
pytest tests/unit/ --cov --cov-report=xml
```

### 4. CI Configuration

```yaml
# .github/workflows/test.yml
- name: Run unit tests
  run: pytest tests/unit/ --cov

# .github/workflows/integration-tests.yml (separate workflow)
- name: Run integration tests
  if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
  env:
    RUN_INTEGRATION_TESTS: 1
    INTEGRATION_TEST_API_KEY: ${{ secrets.INTEGRATION_TEST_API_KEY }}
  run: pytest tests/integration/ --maxfail=3
```

## Improving Mock Accuracy

### 1. Realistic Mock Responses
Base mocks on actual API responses:
```python
@pytest.fixture
def realistic_openrouter_mock():
    """Mock that returns realistic API responses"""
    mock = MagicMock()
    mock.chat.completions.create.return_value = MagicMock(
        choices=[MagicMock(
            message=MagicMock(
                content="Based on the calculation, 2+2 equals 4.",
                role="assistant",
                function_call=None,
                tool_calls=None
            ),
            finish_reason="stop",
            index=0
        )],
        created=1234567890,
        model="anthropic/claude-3-sonnet",
        usage=MagicMock(prompt_tokens=50, completion_tokens=15)
    )
    return mock
```

### 2. Error Scenario Testing
Include real error responses:
```python
def test_rate_limit_handling(mock_openai):
    """Test behavior when API returns rate limit error"""
    mock_openai.side_effect = Exception("Rate limit exceeded")
    agent = create_agent(config, client=mock_openai)
    result = agent.run("Test")
    assert "error" in result.lower()
```

### 3. Response Validation
Periodically validate mock structure:
```python
# scripts/validate_mocks.py
def validate_mock_structure():
    """Compare mock responses against real API"""
    real_response = make_real_api_call()
    mock_response = get_mock_response()
    
    assert set(real_response.keys()) == set(mock_response.keys())
    assert type(real_response['choices']) == type(mock_response['choices'])
```

## Cost Management for Integration Tests

1. **Use Cheaper Models**: 
   - GPT-3.5-turbo instead of GPT-4
   - Claude Haiku instead of Claude Sonnet/Opus
   
2. **Limit Test Scope**:
   - Simple prompts that require minimal tokens
   - Set max_tokens limits in test config
   
3. **Test Account Management**:
   - Separate API key with spending limits
   - Monitor usage through provider dashboards
   
4. **Selective Execution**:
   - Only run on main branch merges
   - Manual trigger for PRs when needed
   - Nightly runs with budget alerts

## Conclusion

This hybrid approach provides:
1. **Fast, reliable CI** through mocked unit tests
2. **Real-world validation** through periodic integration tests  
3. **Cost control** through smart test design and execution
4. **Confidence** that the system works with actual APIs

The key is recognizing that different types of tests serve different purposes. Unit tests verify behavior contracts, while integration tests verify real-world functionality.