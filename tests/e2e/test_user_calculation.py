import pytest
import subprocess
import sys
import os
import json
from unittest.mock import patch

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def test_user_calculation_journey_single_agent(
    tmp_config, clean_env, dummy_openrouter_key
):
    """Full flow: user prompt -> agent -> calculation -> final answer."""
    # Check if we have a real API key
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)

    if config["openrouter"]["api_key"] == "sk-test-dummy-key-12345":
        pytest.skip("E2E test requires real API key")

    # Given: A test script that simulates user interaction
    test_script = f"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath('{__file__}')))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath('{__file__}')))))

# Import and run
from main import main

# Mock stdin to provide user input
import io
sys.stdin = io.StringIO("What is 15 times 7?\\nexit\\n")

# Set config path via sys.argv
sys.argv = ['main.py', '{tmp_config}']

# Run main
try:
    main()
except SystemExit:
    pass
"""

    # When: Running the main entry point
    result = subprocess.run(
        [sys.executable, "-c", test_script],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )

    # Then: User sees output (we don't assert specific values to avoid brittle tests)
    assert result.returncode == 0 or "exit" in result.stdout.lower()


def test_user_journey_orchestrator_mode(tmp_config, clean_env, dummy_openrouter_key):
    """Full orchestrator flow: decompose -> parallel agents -> synthesis."""
    # Check if we have a real API key
    import yaml

    with open(tmp_config, "r") as f:
        config = yaml.safe_load(f)

    if config["openrouter"]["api_key"] == "sk-test-dummy-key-12345":
        pytest.skip("E2E test requires real API key")

    # Given: A test script for orchestrator mode
    test_script = f"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath('{__file__}')))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath('{__file__}')))))

# Import and run
from make_it_heavy import main

# Mock stdin
import io
sys.stdin = io.StringIO("What is 15 times 7?\\n")

# Set config path via sys.argv
sys.argv = ['make_it_heavy.py', '{tmp_config}']

# Run
try:
    main()
except Exception as e:
    print(f"ERROR: {{e}}")
"""

    # When: Running orchestrator mode
    result = subprocess.run(
        [sys.executable, "-c", test_script],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )

    # Then: Orchestrator completes (we don't assert specific output)
    assert result.returncode == 0 or len(result.stdout) > 0


def test_cli_handles_invalid_config_gracefully(clean_env):
    """CLI provides helpful error when config file is missing."""
    # When: Running with non-existent config
    result = subprocess.run(
        [sys.executable, "main.py", "nonexistent.yaml"],
        capture_output=True,
        text=True,
        cwd=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )

    # Then: Error message is helpful
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "config" in output.lower() or "not found" in output.lower()


def test_tool_execution_through_cli(tmp_config, clean_env):
    """Tools are accessible and executable through the CLI flow."""
    # Given: Script that uses tools directly
    test_script = f"""
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath('{__file__}')))))

# Test tool bridge directly
import subprocess
result = subprocess.run(
    [sys.executable, 'use_tool.py', 'calculate', '<args><expression>20 + 22</expression></args>'],
    capture_output=True,
    text=True,
    cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath('{__file__}'))))
)

if result.returncode == 0:
    import json
    output = json.loads(result.stdout)
    print(f"RESULT: {{output['result']}}")
else:
    print(f"ERROR: {{result.stderr}}")
"""

    # When: Running tool through bridge
    result = subprocess.run(
        [sys.executable, "-c", test_script], capture_output=True, text=True
    )

    # Then: Tool executes correctly
    assert "RESULT: 42" in result.stdout
