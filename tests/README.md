# Make It Heavy - Test Suite

This is the behavior-focused test suite for the Make It Heavy framework, built with pytest.

## Test Philosophy

All tests follow these principles:
- **Behavior over implementation**: Test what the code does, not how it does it
- **User perspective**: Test through public APIs as users would interact
- **Deterministic**: Same input always produces same output
- **Isolated**: Each test is independent and can run in any order
- **Fast feedback**: Unit tests run quickly, integration tests are thorough

## Running Tests

### Basic Usage
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run in parallel (limited to 2 workers by default)
pytest -n 2

# Run specific test file
pytest tests/agent/test_factory.py

# Run specific test
pytest tests/agent/test_factory.py::test_create_agent_returns_functional_agent_for_simple_prompt
```

### Using the Test Runner
```bash
# Run all tests
python run_tests.py

# With coverage
python run_tests.py --coverage

# In parallel
python run_tests.py --parallel

# Specific tests
python run_tests.py tests/agent/
```

## Test Categories

### Unit Tests (`tests/agent/`, `tests/tools/`)
- Test individual components in isolation
- Use mocks for external dependencies
- Fast execution (< 0.1s per test)
- Focus on single behaviors

### Integration Tests (`tests/integration/`)
- Test component interactions
- Verify error handling and recovery
- May use some real components

### End-to-End Tests (`tests/e2e/`)
- Test complete user journeys
- Verify CLI functionality
- Simulate real usage patterns


## Key Fixtures (in `conftest.py`)

- `tmp_config`: Creates temporary config file
- `clean_env`: Cleans environment variables
- `mock_openai_client`: Provides deterministic AI responses
- `clean_work_dir`: Isolated working directory per test

## Writing New Tests

1. Focus on behavior, not implementation:
```python
# GOOD: Tests behavior
def test_calculate_returns_correct_result():
    result = calc_tool.execute(expression="2+2")
    assert result['result'] == 4

# BAD: Tests implementation
def test_calculate_calls_eval():
    # Don't test internal implementation details
```

2. Use descriptive test names:
```python
def test_agent_stops_after_max_iterations_exceeded():
    # Clear what behavior is being tested
```

3. Follow Given-When-Then pattern:
```python
def test_example():
    # Given: Setup and context
    config = create_test_config()
    
    # When: Action being tested
    result = perform_action(config)
    
    # Then: Assert expected outcome
    assert result == expected_value
```

## Continuous Integration

Tests are designed to run in CI environments:
- No hardcoded paths
- No network dependencies (mocked)
- Deterministic results
- Clear error messages

## Debugging Failed Tests

1. Run with verbose output: `pytest -vv`
2. Show full traceback: `pytest --tb=long`
3. Drop into debugger: `pytest --pdb`
4. Run single test: `pytest -k "test_name"`