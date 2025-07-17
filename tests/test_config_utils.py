import pytest
import tempfile
import yaml
import threading
import time
from pathlib import Path
from config_utils import (
    load_config, 
    get_agent_config, 
    get_orchestrator_config, 
    validate_config,
    clear_config_cache
)


class TestConfigLoading:
    """Test configuration loading and caching functionality."""
    
    def setup_method(self):
        """Clear cache before each test."""
        clear_config_cache()
    
    def test_load_config_basic(self):
        """Test basic configuration loading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'provider': 'openrouter',
                'openrouter': {
                    'api_key': 'test_key',
                    'model': 'test_model'
                },
                'system_prompt': 'Test prompt'
            }
            yaml.dump(config_data, f)
            f.flush()
            
            config = load_config(f.name)
            assert config['provider'] == 'openrouter'
            assert config['openrouter']['api_key'] == 'test_key'
            
            Path(f.name).unlink()
    
    def test_config_caching(self):
        """Test that configurations are cached properly."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'provider': 'openrouter',
                'openrouter': {
                    'api_key': 'test_key',
                    'model': 'test_model'
                }
            }
            yaml.dump(config_data, f)
            f.flush()
            
            # First load
            config1 = load_config(f.name)
            
            # Modify file
            config_data['provider'] = 'claude_code'
            config_data['claude_code'] = {
                'model': 'claude-3-sonnet'
            }
            with open(f.name, 'w') as f2:
                yaml.dump(config_data, f2)
            
            # Second load should return cached version
            config2 = load_config(f.name)
            assert config2['provider'] == 'openrouter'  # Still cached value
            
            # Clear cache and reload
            clear_config_cache()
            config3 = load_config(f.name)
            assert config3['provider'] == 'claude_code'  # New value
            
            Path(f.name).unlink()
    
    def test_thread_safe_caching(self):
        """Test thread-safe configuration loading."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            config_data = {
                'provider': 'openrouter',
                'openrouter': {
                    'api_key': 'test_key',
                    'model': 'test_model'
                }
            }
            yaml.dump(config_data, f)
            f.flush()
            
            results = []
            
            def load_in_thread():
                config = load_config(f.name)
                results.append(config)
            
            # Create multiple threads
            threads = []
            for _ in range(10):
                t = threading.Thread(target=load_in_thread)
                threads.append(t)
                t.start()
            
            # Wait for all threads
            for t in threads:
                t.join()
            
            # All should have same config
            assert len(results) == 10
            for config in results:
                assert config['provider'] == 'openrouter'
            
            Path(f.name).unlink()


class TestConfigValidation:
    """Test configuration validation."""
    
    def test_validate_missing_provider(self):
        """Test validation fails with missing provider."""
        config = {
            'openrouter': {
                'api_key': 'test_key'
            }
        }
        with pytest.raises(ValueError, match="Missing required configuration field: provider"):
            validate_config(config)
    
    def test_validate_missing_provider_config(self):
        """Test validation fails when provider config missing."""
        config = {
            'provider': 'openrouter'
        }
        with pytest.raises(ValueError, match="Provider 'openrouter' configuration not found"):
            validate_config(config)
    
    def test_validate_openrouter_missing_fields(self):
        """Test validation for OpenRouter required fields."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key'
                # Missing model
            }
        }
        with pytest.raises(ValueError, match="OpenRouter provider requires 'model'"):
            validate_config(config)
    
    def test_validate_claude_code_missing_fields(self):
        """Test validation for Claude Code required fields."""
        config = {
            'provider': 'claude_code',
            'claude_code': {
                # Missing model
            }
        }
        with pytest.raises(ValueError, match="Claude Code provider requires 'model'"):
            validate_config(config)
    
    def test_validate_agent_unknown_provider(self):
        """Test validation fails for agent with unknown provider."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'agents': {
                'agent_1': {
                    'provider': 'unknown_provider'
                }
            }
        }
        with pytest.raises(ValueError, match="Agent 'agent_1' references unknown provider"):
            validate_config(config)
    
    def test_validate_orchestrator_unknown_provider(self):
        """Test validation fails for orchestrator with unknown provider."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'orchestrator': {
                'provider': 'unknown_provider'
            }
        }
        with pytest.raises(ValueError, match="Orchestrator references unknown provider"):
            validate_config(config)
    
    def test_validate_valid_config(self):
        """Test validation passes for valid configuration."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'claude_code': {
                'model': 'claude-3'
            },
            'agents': {
                'agent_1': {
                    'provider': 'claude_code',
                    'model': 'claude-3.5'
                }
            },
            'orchestrator': {
                'provider': 'openrouter',
                'model': 'gpt-4'
            }
        }
        assert validate_config(config) is True


class TestAgentConfig:
    """Test agent configuration inheritance."""
    
    def test_agent_config_inheritance_default(self):
        """Test default agent configuration."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'system_prompt': 'Global prompt',
            'agent': {
                'max_iterations': 5
            }
        }
        
        agent_config = get_agent_config(config)
        assert agent_config['provider'] == 'openrouter'
        assert agent_config['system_prompt'] == 'Global prompt'
        assert agent_config['max_iterations'] == 5
        assert agent_config['api_key'] == 'test_key'
        assert agent_config['model'] == 'test_model'
    
    def test_agent_config_specific_override(self):
        """Test agent-specific configuration overrides."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'global_key',
                'model': 'global_model'
            },
            'system_prompt': 'Global prompt',
            'agents': {
                'agent_1': {
                    'model': 'agent_model',
                    'system_prompt': 'Agent prompt'
                }
            }
        }
        
        agent_config = get_agent_config(config, 'agent_1')
        assert agent_config['provider'] == 'openrouter'
        assert agent_config['system_prompt'] == 'Agent prompt'
        assert agent_config['model'] == 'agent_model'
        assert agent_config['api_key'] == 'global_key'  # Inherited
    
    def test_agent_config_provider_override(self):
        """Test agent with different provider."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'or_key',
                'model': 'or_model'
            },
            'claude_code': {
                'model': 'claude_model',
                'max_turns': 10
            },
            'agents': {
                'agent_1': {
                    'provider': 'claude_code',
                    'system_prompt': 'Custom prompt'
                }
            }
        }
        
        agent_config = get_agent_config(config, 'agent_1')
        assert agent_config['provider'] == 'claude_code'
        assert agent_config['model'] == 'claude_model'
        assert agent_config['max_turns'] == 10
        assert agent_config['system_prompt'] == 'Custom prompt'
        # Note: api_key from openrouter remains due to config merge behavior
        assert agent_config['api_key'] == 'or_key'
    
    def test_agent_config_nonexistent_agent(self):
        """Test configuration for non-existent agent uses defaults."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'agents': {
                'agent_1': {
                    'model': 'custom_model'
                }
            }
        }
        
        agent_config = get_agent_config(config, 'agent_2')
        assert agent_config['provider'] == 'openrouter'
        assert agent_config['model'] == 'test_model'  # Global model


class TestOrchestratorConfig:
    """Test orchestrator configuration."""
    
    def test_orchestrator_config_default(self):
        """Test default orchestrator configuration."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'test_model'
            },
            'orchestrator': {
                'parallel_agents': 4,
                'task_timeout': 300
            }
        }
        
        orch_config = get_orchestrator_config(config)
        assert orch_config['parallel_agents'] == 4
        assert orch_config['task_timeout'] == 300
        assert orch_config['api_key'] == 'test_key'
        assert orch_config['model'] == 'test_model'
    
    def test_orchestrator_config_provider_override(self):
        """Test orchestrator with different provider."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'or_key',
                'model': 'or_model'
            },
            'claude_code': {
                'model': 'claude_model'
            },
            'orchestrator': {
                'provider': 'claude_code',
                'model': 'orch_model'
            }
        }
        
        orch_config = get_orchestrator_config(config)
        assert orch_config['provider'] == 'claude_code'
        assert orch_config['model'] == 'orch_model'
        assert 'api_key' not in orch_config
    
    def test_orchestrator_config_model_override_only(self):
        """Test orchestrator with model override but same provider."""
        config = {
            'provider': 'openrouter',
            'openrouter': {
                'api_key': 'test_key',
                'model': 'default_model'
            },
            'orchestrator': {
                'model': 'orchestrator_model'
            }
        }
        
        orch_config = get_orchestrator_config(config)
        assert orch_config['api_key'] == 'test_key'
        assert orch_config['model'] == 'orchestrator_model'