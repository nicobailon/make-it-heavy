import pytest
import tempfile
import yaml
from unittest.mock import Mock, patch
from agent import create_agent, create_agent_legacy, _create_agent_original
from config_utils import clear_config_cache


class TestEnhancedAgentFactory:
    """Test enhanced agent factory with agent-specific configuration."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_config_cache()
    
    def create_test_config(self, config_data):
        """Helper to create temporary config file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            f.flush()
            return f.name
    
    @patch('agent.OpenRouterAgent')
    def test_create_agent_basic(self, mock_agent_class):
        """Test basic agent creation with global config."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'system_prompt': 'Test prompt'
        }
        config_path = self.create_test_config(config_data)
        
        mock_instance = Mock()
        mock_agent_class.return_value = mock_instance
        
        agent = create_agent(config_path=config_path)
        
        # Verify agent was created with correct config
        mock_agent_class.assert_called_once()
        call_args = mock_agent_class.call_args
        assert call_args.kwargs['config_path'] == config_path
        assert call_args.kwargs['silent'] == False
        assert 'agent_config' in call_args.kwargs
        
        agent_config = call_args.kwargs['agent_config']
        assert agent_config['provider'] == 'openrouter'
        assert agent_config['model'] == 'test_model'
        assert agent_config['system_prompt'] == 'Test prompt'
    
    @patch('agent.OpenRouterAgent')
    def test_create_agent_with_agent_id(self, mock_agent_class):
        """Test agent creation with specific agent ID."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'global_key',
                'model': 'global_model'
            },
            'system_prompt': 'Global prompt',
            'agents': {
                'agent_1': {
                    'model': 'agent1_model',
                    'system_prompt': 'Agent 1 prompt'
                }
            }
        }
        config_path = self.create_test_config(config_data)
        
        mock_instance = Mock()
        mock_agent_class.return_value = mock_instance
        
        agent = create_agent(config_path=config_path, agent_id='agent_1')
        
        # Verify agent config has agent-specific values
        call_args = mock_agent_class.call_args
        agent_config = call_args.kwargs['agent_config']
        assert agent_config['model'] == 'agent1_model'
        assert agent_config['system_prompt'] == 'Agent 1 prompt'
        assert agent_config['api_key'] == 'global_key'  # Inherited
    
    @patch('claude_code_cli_provider.ClaudeCodeCLIAgent')
    @patch('agent.OpenRouterAgent')
    def test_create_agent_provider_override(self, mock_or_agent, mock_cc_agent):
        """Test agent with different provider than global."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'or_key',
                'model': 'or_model'
            },
            'claude_code': {
                'model': 'cc_model'
            },
            'agents': {
                'agent_1': {
                    'provider': 'claude_code',
                    'model': 'agent_cc_model'
                }
            }
        }
        config_path = self.create_test_config(config_data)
        
        mock_instance = Mock()
        mock_cc_agent.return_value = mock_instance
        
        agent = create_agent(config_path=config_path, agent_id='agent_1')
        
        # Should create Claude Code agent, not OpenRouter
        mock_cc_agent.assert_called_once()
        mock_or_agent.assert_not_called()
        
        # Verify correct model passed
        call_args = mock_cc_agent.call_args
        agent_config = call_args.kwargs['agent_config']
        assert agent_config['provider'] == 'claude_code'
        assert agent_config['model'] == 'agent_cc_model'
    
    @patch('agent.OpenRouterAgent')
    def test_create_agent_with_preloaded_config(self, mock_agent_class):
        """Test agent creation with pre-loaded configuration."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            }
        }
        
        mock_instance = Mock()
        mock_agent_class.return_value = mock_instance
        
        # Create agent with pre-loaded config (no file read)
        agent = create_agent(config_path='dummy_path', preloaded_config=config_data)
        
        # Should not raise file not found error
        mock_agent_class.assert_called_once()
    
    def test_create_agent_legacy_compatibility(self):
        """Test legacy function still works."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            }
        }
        config_path = self.create_test_config(config_data)
        
        with patch('agent.OpenRouterAgent') as mock_agent:
            mock_instance = Mock()
            mock_agent.return_value = mock_instance
            
            # Test legacy function
            agent = create_agent_legacy(config_path=config_path)
            
            # Should work without agent_id
            mock_agent.assert_called_once()
            call_args = mock_agent.call_args
            assert 'agent_config' in call_args.kwargs
    
    def test_create_agent_original_preserved(self):
        """Test original function is preserved."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            }
        }
        config_path = self.create_test_config(config_data)
        
        with patch('agent.OpenRouterAgent') as mock_agent:
            mock_instance = Mock()
            mock_agent.return_value = mock_instance
            
            # Test original function
            agent = _create_agent_original(config_path=config_path)
            
            # Should NOT have agent_config parameter
            mock_agent.assert_called_once()
            call_args = mock_agent.call_args
            assert 'agent_config' not in call_args.kwargs
    
    @patch('agent.OpenRouterAgent')
    def test_create_agent_validation_failure(self, mock_agent_class):
        """Test agent creation fails with invalid config."""
        config_data = {
            # Missing provider
            'openrouter': {
                'api_key': 'test_key'
            }
        }
        config_path = self.create_test_config(config_data)
        
        with pytest.raises(ValueError, match="Missing required configuration field"):
            create_agent(config_path=config_path)
    
    @patch('claude_code_cli_provider.ClaudeCodeCLIAgent')
    def test_create_agent_claude_code_default(self, mock_agent_class):
        """Test Claude Code agent creation."""
        config_data = {
            'provider': 'claude_code',
            'claude_code': {
                'model': 'claude-3',
                'max_turns': 10
            },
            'system_prompt': 'Test prompt'
        }
        config_path = self.create_test_config(config_data)
        
        mock_instance = Mock()
        mock_agent_class.return_value = mock_instance
        
        agent = create_agent(config_path=config_path)
        
        # Verify Claude Code agent created
        mock_agent_class.assert_called_once()
        call_args = mock_agent_class.call_args
        agent_config = call_args.kwargs['agent_config']
        assert agent_config['provider'] == 'claude_code'
        assert agent_config['model'] == 'claude-3'


class TestBackwardCompatibility:
    """Test backward compatibility is maintained."""
    
    def test_imports_still_work(self):
        """Test existing imports continue to work."""
        # Should be able to import create_agent directly
        from agent import create_agent
        assert callable(create_agent)
        
        # Legacy function should exist
        from agent import create_agent_legacy
        assert callable(create_agent_legacy)
    
    @patch('agent.OpenRouterAgent')
    def test_old_usage_pattern(self, mock_agent_class):
        """Test old usage pattern still works."""
        config_data = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            }
        }
        config_path = tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False).name
        with open(config_path, 'w') as f:
            yaml.dump(config_data, f)
        
        mock_instance = Mock()
        mock_agent_class.return_value = mock_instance
        
        # Old usage: just config_path and silent
        agent = create_agent(config_path, silent=True)
        
        # Should work
        mock_agent_class.assert_called_once()
        assert mock_agent_class.call_args.kwargs['silent'] == True