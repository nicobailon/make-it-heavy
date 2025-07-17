import pytest
import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)

from tools import discover_tools


def test_calculate_tool_returns_correct_numerical_result(base_config_dict):
    """Calculate tool returns correct numerical result for expressions."""
    # Given: Calculate tool
    tools = discover_tools(base_config_dict, silent=True)
    calc_tool = tools.get("calculate")

    if not calc_tool:
        pytest.skip("Calculate tool not available")

    # When/Then: Various calculations return correct results
    test_cases = [
        ("2+2", 4),
        ("10*5", 50),
        ("100/4", 25),
        ("3**2", 9),
        ("sqrt(16)", 4),
    ]

    for expression, expected in test_cases:
        result = calc_tool.execute(expression=expression)
        assert result["result"] == expected, f"Failed for {expression}"


def test_file_operations_create_and_read_files(base_config_dict, tmp_path):
    """Write and read file tools work together correctly."""
    # Given: File tools
    tools = discover_tools(base_config_dict, silent=True)
    write_tool = tools.get("write_file")
    read_tool = tools.get("read_file")

    if not write_tool or not read_tool:
        pytest.skip("File tools not available")

    # When: Writing a file
    test_file = str(tmp_path / "test_file.txt")
    test_content = "Hello, this is test content!\nLine 2"

    write_result = write_tool.execute(path=test_file, content=test_content)
    assert write_result.get("success") is True or "error" not in write_result

    # Then: Reading returns the same content
    read_result = read_tool.execute(path=test_file)
    assert test_content in str(read_result.get("content", ""))


def test_search_tool_returns_results_or_handles_network_error(base_config_dict):
    """Search tool either returns results or gracefully handles network issues."""
    from unittest.mock import patch, MagicMock
    
    # Given: Search tool with mocked network calls
    tools = discover_tools(base_config_dict, silent=True)
    search_tool = tools.get("search_web")

    if not search_tool:
        pytest.skip("Search tool not available")

    # Mock DDGS search results
    mock_search_results = [
        {
            'title': 'Python Programming Guide',
            'href': 'https://example.com/python',
            'body': 'Learn Python programming basics...'
        },
        {
            'title': 'Advanced Python',
            'href': 'https://example.com/advanced',
            'body': 'Advanced Python techniques...'
        }
    ]
    
    # Mock requests.get response
    mock_response = MagicMock()
    mock_response.text = '<html><body><p>Python is a great programming language.</p></body></html>'
    mock_response.raise_for_status = MagicMock()
    
    with patch('tools.search_tool.DDGS') as mock_ddgs_class:
        with patch('tools.search_tool.requests.get') as mock_requests:
            # Configure mocks
            mock_ddgs = MagicMock()
            mock_ddgs.text.return_value = mock_search_results
            mock_ddgs_class.return_value = mock_ddgs
            
            mock_requests.return_value = mock_response
            
            # When: Searching
            result = search_tool.execute(query="Python programming")
            
            # Then: Returns results (not error since we mocked successful response)
            assert isinstance(result, list)
            assert len(result) == 2
            assert result[0]['title'] == 'Python Programming Guide'
            assert 'content' in result[0]
            assert 'Python is a great programming language' in result[0]['content']


def test_task_complete_tool_marks_completion(base_config_dict):
    """mark_task_complete tool returns completion confirmation."""
    # Given: Task complete tool
    tools = discover_tools(base_config_dict, silent=True)
    complete_tool = tools.get("mark_task_complete")

    if not complete_tool:
        pytest.skip("Task complete tool not available")

    # When: Marking task complete
    result = complete_tool.execute(
        task_summary="Test task", completion_message="Successfully completed"
    )

    # Then: Returns completion status
    assert result.get("completed") is True or "success" in str(result).lower()


def test_tools_handle_edge_cases_gracefully(base_config_dict, tmp_path):
    """Tools handle edge cases without crashing."""
    tools = discover_tools(base_config_dict, silent=True)

    # Test calculate with invalid expression
    if "calculate" in tools:
        result = tools["calculate"].execute(expression="invalid math")
        assert "error" in result or "result" in result  # Should handle gracefully

    # Test read non-existent file
    if "read_file" in tools:
        result = tools["read_file"].execute(path=str(tmp_path / "nonexistent.txt"))
        assert "error" in result or "content" in result  # Should handle gracefully

    # Test write to invalid path
    if "write_file" in tools:
        result = tools["write_file"].execute(
            path="/invalid/path/file.txt", content="test"
        )
        assert "error" in result or "success" in result  # Should handle gracefully
