import yaml
import threading
import copy
from typing import Dict, Any, Optional
from pathlib import Path

# Thread-safe configuration cache
_config_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load and validate configuration file with caching for performance"""
    # Check cache first
    config_path_str = str(Path(config_path).resolve())
    
    with _cache_lock:
        if config_path_str in _config_cache:
            return copy.deepcopy(_config_cache[config_path_str])
    
    # Load configuration
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate before caching
    validate_config(config)
    
    # Cache the configuration
    with _cache_lock:
        _config_cache[config_path_str] = config
    
    return copy.deepcopy(config)

def get_agent_config(config: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Get configuration for specific agent with inheritance

    Priority: agent_specific > global > defaults
    """
    # Start with global defaults
    agent_config = {
        'provider': config.get('provider', 'openrouter'),
        'system_prompt': config.get('system_prompt', ''),
        'max_iterations': config.get('agent', {}).get('max_iterations', 10)
    }

    # Add provider-specific defaults
    provider = agent_config['provider']
    if provider in config:
        agent_config.update(config[provider])

    # Override with agent-specific configuration if provided
    if agent_id and 'agents' in config and agent_id in config['agents']:
        agent_specific = config['agents'][agent_id]
        agent_config.update(agent_specific)

        # Handle provider override
        if 'provider' in agent_specific:
            new_provider = agent_specific['provider']
            if new_provider in config:
                # Merge provider-specific settings
                provider_config = config[new_provider].copy()
                provider_config.update(agent_specific)
                agent_config.update(provider_config)

    return agent_config

def get_orchestrator_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Get orchestrator-specific configuration with model overrides"""
    orchestrator_config = config.get('orchestrator', {}).copy()

    # Add model configuration if specified
    if 'provider' in orchestrator_config:
        provider = orchestrator_config['provider']
        if provider in config:
            # Merge provider settings but prioritize orchestrator overrides
            provider_config = config[provider].copy()
            provider_config.update(orchestrator_config)
            orchestrator_config = provider_config
    else:
        # Use global provider settings
        global_provider = config.get('provider', 'openrouter')
        if global_provider in config:
            base_config = config[global_provider].copy()
            base_config.update(orchestrator_config)
            orchestrator_config = base_config

    return orchestrator_config

def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration structure and required fields"""
    # Import constants from existing module
    from constants import DEFAULT_CLI_VERIFICATION_TIMEOUT
    
    required_fields = ['provider']

    for field in required_fields:
        if field not in config:
            raise ValueError(f"Missing required configuration field: {field}")

    # Validate provider configuration
    provider = config['provider']
    if provider not in config:
        raise ValueError(f"Provider '{provider}' configuration not found")
    
    # Validate provider-specific required fields
    if provider == 'openrouter':
        if 'api_key' not in config['openrouter']:
            raise ValueError("OpenRouter provider requires 'api_key'")
        if 'model' not in config['openrouter']:
            raise ValueError("OpenRouter provider requires 'model'")
    elif provider == 'claude_code':
        if 'model' not in config['claude_code']:
            raise ValueError("Claude Code provider requires 'model'")
        # Validate CLI timeout if specified in timeouts block
        if 'timeouts' in config and 'cli_verification' in config['timeouts']:
            timeout = config['timeouts']['cli_verification']
            if timeout > DEFAULT_CLI_VERIFICATION_TIMEOUT:
                raise ValueError(f"CLI verification timeout {timeout} exceeds maximum {DEFAULT_CLI_VERIFICATION_TIMEOUT}")

    # Validate agent configurations
    if 'agents' in config:
        for agent_id, agent_config in config['agents'].items():
            if 'provider' in agent_config:
                agent_provider = agent_config['provider']
                if agent_provider not in config:
                    raise ValueError(f"Agent '{agent_id}' references unknown provider '{agent_provider}'")
                
                # Validate agent has required fields for its provider
                if agent_provider == 'openrouter' and 'model' not in agent_config:
                    # Must inherit from global or specify model
                    if 'model' not in config['openrouter']:
                        raise ValueError(f"Agent '{agent_id}' using OpenRouter must specify a model")
    
    # Validate orchestrator configuration if present
    if 'orchestrator' in config:
        orch_config = config['orchestrator']
        if 'provider' in orch_config:
            orch_provider = orch_config['provider']
            if orch_provider not in config:
                raise ValueError(f"Orchestrator references unknown provider '{orch_provider}'")

    return True

def clear_config_cache():
    """Clear the configuration cache (useful for testing)"""
    with _cache_lock:
        _config_cache.clear()