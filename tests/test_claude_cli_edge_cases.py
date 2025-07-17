"""CPU-friendly tests for Claude CLI edge cases and installation scenarios."""
import pytest
import subprocess
from unittest.mock import patch, MagicMock, call
import json
import os
from claude_code_cli_provider import ClaudeCodeCLIAgent
from exceptions import CLINotFoundError, CLIVerificationError, StreamingParseError


@pytest.fixture
def mock_config():
    """Minimal config for testing."""
    return {
        'claude_code': {
            'model': 'test-model',
            'max_turns': 5,
            'cli_path': 'claude'
        },
        'agent': {'max_iterations': 5},
        'system_prompt': 'Test prompt',
        'timeouts': {
            'cli_verification': 1,  # Short timeout for tests
            'progress_update_interval': 1
        },
        'display': {
            'preview_lines': 5,
            'preview_display_lines': 3,
            'line_truncate_length': 50,
            'json_preview_length': 30,
            'max_prompt_size': 1000
        },
        'performance': {
            'cache_tool_discovery': False,  # Disable for tests
            'cache_system_prompts': False
        }
    }


def test_cli_not_installed(mock_config, tmp_path):
    """Test error when Claude CLI is not installed."""
    # Given: Config pointing to non-existent CLI
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    # Mock subprocess to simulate CLI not found
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = FileNotFoundError()
        
        # When/Then: Creating agent raises CLINotFoundError
        with pytest.raises(CLINotFoundError) as exc_info:
            ClaudeCodeCLIAgent(str(config_path), silent=True)
        
        assert 'claude' in str(exc_info.value)
        assert 'npm install' in str(exc_info.value)


def test_cli_verification_timeout(mock_config, tmp_path):
    """Test handling of CLI verification timeout."""
    # Given: Config with short timeout
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    # Mock subprocess to simulate timeout
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired('claude', 1)
        
        # When/Then: Creating agent raises CLIVerificationError
        with pytest.raises(CLIVerificationError) as exc_info:
            ClaudeCodeCLIAgent(str(config_path), silent=True)
        
        assert 'timed out' in str(exc_info.value).lower()


def test_cli_returns_error(mock_config, tmp_path):
    """Test handling when CLI returns non-zero exit code."""
    # Given: Config file
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    # Mock subprocess to return error
    with patch('subprocess.run') as mock_run:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Invalid CLI arguments"
        mock_run.return_value = mock_result
        
        # When/Then: Creating agent raises CLIVerificationError
        with pytest.raises(CLIVerificationError) as exc_info:
            ClaudeCodeCLIAgent(str(config_path), silent=True)
        
        assert 'Invalid CLI arguments' in str(exc_info.value)


def test_streaming_json_parse_errors(mock_config, tmp_path):
    """Test handling of malformed JSON in streaming output."""
    # Given: Agent with mocked subprocess
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    with patch('subprocess.run') as mock_run:
        # Mock successful verification
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        # Mock tool discovery
        with patch('tools.discover_tools') as mock_discover:
            mock_discover.return_value = {}
            
            agent = ClaudeCodeCLIAgent(str(config_path), silent=True)
            
            # Mock Popen for streaming
            with patch('subprocess.Popen') as mock_popen:
                mock_process = MagicMock()
                mock_popen.return_value = mock_process
                
                # Simulate mixed valid/invalid JSON lines
                mock_process.stdout = [
                    b'{"type": "system", "subtype": "init", "model": "test"}\n',
                    b'INVALID JSON LINE\n',
                    b'{"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}}\n',
                    b'{"broken": json}\n',
                    b'{"type": "result", "subtype": "success", "result": "Done"}\n'
                ]
                mock_process.stderr.read.return_value = b''
                mock_process.wait.return_value = None
                mock_process.returncode = 0
                
                # When: Running the agent
                result = agent.run("Test prompt")
                
                # Then: Valid messages are processed, invalid ones skipped
                assert "Hello" in result
                assert "Done" in result


def test_large_prompt_truncation(mock_config, tmp_path):
    """Test that large prompts are truncated properly."""
    # Given: Config with small max prompt size
    mock_config['display']['max_prompt_size'] = 200
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        # Create many mock tools to exceed prompt size
        with patch('tools.discover_tools') as mock_discover:
            mock_tools = {}
            for i in range(20):
                tool = MagicMock()
                tool.description = f"This is a very long description for tool {i}"
                mock_tools[f'tool_{i}'] = tool
            mock_discover.return_value = mock_tools
            
            # When: Creating agent
            agent = ClaudeCodeCLIAgent(str(config_path), silent=True)
            
            # Then: System prompt is truncated
            assert len(agent.system_prompt) <= 200
            assert "[Prompt truncated due to size limit]" in agent.system_prompt


def test_max_iterations_reached(mock_config, tmp_path):
    """Test handling when max iterations are reached."""
    # Given: Config with low max turns
    mock_config['claude_code']['max_turns'] = 2
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        with patch('tools.discover_tools') as mock_discover:
            mock_discover.return_value = {}
            
            agent = ClaudeCodeCLIAgent(str(config_path), silent=True)
            
            with patch('subprocess.Popen') as mock_popen:
                mock_process = MagicMock()
                mock_popen.return_value = mock_process
                
                # Simulate reaching max turns
                mock_process.stdout = [
                    b'{"type": "assistant", "message": {"content": [{"type": "text", "text": "Turn 1"}]}}\n',
                    b'{"type": "assistant", "message": {"content": [{"type": "text", "text": "Turn 2"}]}}\n',
                    b'{"type": "result", "subtype": "error_max_turns", "is_error": true}\n'
                ]
                mock_process.stderr.read.return_value = b''
                mock_process.wait.return_value = None
                mock_process.returncode = 0
                
                # When: Running the agent
                result = agent.run("Keep going")
                
                # Then: Both turns are included
                assert "Turn 1" in result
                assert "Turn 2" in result


def test_cli_path_configuration(mock_config, tmp_path):
    """Test using custom CLI path from config."""
    # Given: Config with custom CLI path
    custom_path = '/custom/path/to/claude'
    mock_config['claude_code']['cli_path'] = custom_path
    config_path = tmp_path / "config.yaml"
    with open(config_path, 'w') as f:
        import yaml
        yaml.dump(mock_config, f)
    
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        
        with patch('tools.discover_tools') as mock_discover:
            mock_discover.return_value = {}
            
            # When: Creating agent
            agent = ClaudeCodeCLIAgent(str(config_path), silent=True)
            
            # Then: Custom path is used
            assert agent.cli_path == custom_path
            # Verify run was called with custom path
            mock_run.assert_called_with(
                [custom_path, '--help'],
                capture_output=True,
                text=True,
                timeout=1
            )