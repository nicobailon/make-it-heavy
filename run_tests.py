#!/usr/bin/env python3
"""
Test runner for the Make It Heavy test suite.
This replaces the old superficial test runner with the new pytest-based suite.
"""

import subprocess
import sys
import os


def main():
    """Run the pytest test suite with appropriate options."""
    print("=== Make It Heavy - Behavior-Focused Test Suite ===")
    print("Running comprehensive tests with pytest...\n")

    # Base pytest command
    cmd = [sys.executable, "-m", "pytest"]

    # Add coverage if requested
    if "--coverage" in sys.argv:
        cmd.extend(["--cov=.", "--cov-report=term-missing"])

    # Add parallel execution if requested
    if "--parallel" in sys.argv:
        cmd.extend(["-n", "2"])

    # Add specific test selection if provided
    test_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    if test_args:
        cmd.extend(test_args)

    # Run pytest
    result = subprocess.run(cmd, cwd=os.path.dirname(os.path.abspath(__file__)))

    # Exit with pytest's exit code
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
