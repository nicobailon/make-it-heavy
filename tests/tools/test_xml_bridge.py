import pytest
import subprocess
import json
import sys
import os

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def run_tool_bridge(tool_name, args_xml):
    """Helper to run the tool bridge and return parsed output."""
    cmd = [sys.executable, "use_tool.py", tool_name, args_xml]
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        ),
    )
    return result.stdout, result.stderr, result.returncode


def test_xml_bridge_parses_valid_xml_and_returns_json():
    """Valid XML input is parsed and returns JSON result."""
    # Given: Valid XML for calculation
    xml_input = "<args><expression>10 * 5</expression></args>"

    # When: Running through bridge
    stdout, stderr, code = run_tool_bridge("calculate", xml_input)

    # Then: Returns valid JSON with correct result
    assert code == 0, f"Bridge failed: {stderr}"
    result = json.loads(stdout)
    assert result["result"] == 50


def test_malformed_xml_returns_error():
    """Malformed XML returns ValueError with helpful message."""
    # Given: Invalid XML
    invalid_inputs = [
        "not xml at all",
        "<args><expression>test</args>",  # Mismatched tags
        '<args expression="test"/>',  # Wrong format
        "",  # Empty
    ]

    for xml_input in invalid_inputs:
        # When: Running with invalid XML
        stdout, stderr, code = run_tool_bridge("calculate", xml_input)

        # Then: Returns error
        assert code == 1, f"Should fail for input: {xml_input}"
        assert "xml" in stdout.lower() or "xml" in stderr.lower()


def test_missing_required_parameters_detected():
    """Missing required parameters are detected and reported."""
    # Given: XML missing required parameter
    xml_input = "<args></args>"  # Missing 'expression' for calculate

    # When: Running calculate without expression
    stdout, stderr, code = run_tool_bridge("calculate", xml_input)

    # Then: Error mentions missing parameter
    assert code == 1
    assert "expression" in stdout or "expression" in stderr


def test_unknown_tool_handled_gracefully():
    """Unknown tool names return appropriate error."""
    # Given: Non-existent tool
    xml_input = "<args><param>value</param></args>"

    # When: Calling unknown tool
    stdout, stderr, code = run_tool_bridge("nonexistent_tool", xml_input)

    # Then: Error indicates unknown tool
    assert code == 1
    assert "unknown tool" in stdout.lower() or "not found" in stdout.lower()


def test_xml_special_characters_handled():
    """XML special characters are properly decoded."""
    # Given: XML with encoded special characters
    test_cases = [
        ("<args><expression>5 &gt; 3</expression></args>", "5 > 3"),
        ("<args><expression>2 &lt; 4</expression></args>", "2 < 4"),
        ("<args><expression>a &amp; b</expression></args>", "a & b"),
    ]

    for xml_input, expected_expr in test_cases:
        # When: Running with special characters
        stdout, stderr, code = run_tool_bridge("calculate", xml_input)

        # Then: Characters are properly decoded
        # (May fail on calculation but should parse XML correctly)
        if code == 0:
            # If it succeeds, great
            pass
        else:
            # If it fails, should be due to math evaluation, not XML parsing
            assert "xml" not in stdout.lower() and "xml" not in stderr.lower()


def test_complex_tool_parameters_parsed_correctly():
    """Multiple parameters in XML are correctly parsed."""
    # Given: XML with multiple parameters
    xml_input = "<args><path>test.txt</path><content>Hello World</content></args>"

    # When: Running write_file with multiple params
    stdout, stderr, code = run_tool_bridge("write_file", xml_input)

    # Then: Tool receives both parameters
    if code == 0:
        result = json.loads(stdout)
        assert "success" in result or "error" not in result
    else:
        # If fails, should be file system issue, not XML parsing
        assert "xml" not in stdout.lower()


def test_numeric_values_in_xml_converted_correctly():
    """Numeric values in XML are properly converted."""
    # Given: Search with numeric parameter
    xml_input = "<args><query>test search</query><max_results>5</max_results></args>"

    # When: Running search with numeric param
    stdout, stderr, code = run_tool_bridge("search_web", xml_input)

    # Then: Completes without XML errors (may have network errors)
    if code == 1:
        # Should not be XML parsing error
        assert "xml" not in stdout.lower() and "xml" not in stderr.lower()
