import yaml
import threading
import copy
import json
from typing import Dict, Any, Optional, List
from pathlib import Path
from collections import ChainMap

# Thread-safe configuration cache
_config_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()

# Cache invalidation support for LRU cache
_cache_generation = 0

# Numeric bounds for configuration values
NUMERIC_BOUNDS = {
    'max_iterations': (1, 100),
    'parallel_agents': (1, 10),
    'timeout': (1, 3600),
    'max_turns': (1, 50),
    'task_timeout': (1, 3600),
    'cli_verification': (1, 3600)
}


class ConfigProxy:
    """Proxy for configuration that implements copy-on-write
    
    This class wraps a configuration dictionary and only creates a deep copy
    when the configuration is modified, improving performance for read-only access.
    """
    def __init__(self, config: Dict[str, Any], copied: bool = False):
        self._config = config
        self._copied = copied
        self._modified = False
    
    def _ensure_copy(self):
        """Create a deep copy only when needed"""
        if not self._copied and not self._modified:
            self._config = copy.deepcopy(self._config)
            self._copied = True
            self._modified = True
    
    def get(self, key, default=None):
        """Get a value from the configuration"""
        return self._config.get(key, default)
    
    def __getitem__(self, key):
        """Get a value using dictionary syntax"""
        return self._config[key]
    
    def __setitem__(self, key, value):
        """Set a value using dictionary syntax (triggers copy)"""
        self._ensure_copy()
        self._config[key] = value
    
    def __contains__(self, key):
        """Check if key exists in configuration"""
        return key in self._config
    
    def update(self, other):
        """Update configuration with another dictionary (triggers copy)"""
        self._ensure_copy()
        self._config.update(other)
    
    def to_dict(self):
        """Convert to a regular dictionary"""
        return self._config if self._modified else copy.deepcopy(self._config)

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load and validate configuration file with caching for performance
    
    Uses ConfigProxy for copy-on-write optimization.
    """
    # Handle None config_path
    if config_path is None:
        config_path = "config.yaml"
        
    # Check cache first
    config_path_str = str(Path(config_path).resolve())
    
    with _cache_lock:
        if config_path_str in _config_cache:
            # Return using ConfigProxy for copy-on-write
            return ConfigProxy(_config_cache[config_path_str], copied=False).to_dict()
    
    # Load configuration
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Validate before caching
    validate_config(config)
    
    # Cache the configuration
    with _cache_lock:
        _config_cache[config_path_str] = config
    
    # Return using ConfigProxy for copy-on-write
    return ConfigProxy(config, copied=False).to_dict()


def _merge_provider_config(agent_specific: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """Merge provider-specific configuration with agent configuration
    
    Uses ChainMap for cleaner precedence handling where agent-specific
    settings override provider defaults.
    
    Parameters
    ----------
    agent_specific : dict
        Agent-specific configuration
    config : dict
        Full configuration with provider sections
        
    Returns
    -------
    dict
        Merged configuration with proper precedence
    """
    provider = agent_specific.get('provider')
    if provider and provider in config:
        # Use ChainMap for cleaner precedence handling
        # agent_specific takes precedence over provider defaults
        return dict(ChainMap(agent_specific, config[provider]))
    return agent_specific


# Cache for computed agent configurations
_agent_config_cache: Dict[str, Dict[str, Any]] = {}
_cache_max_size = 128


def _compute_agent_config(config: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
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
        
        # Handle provider override with simplified logic
        if 'provider' in agent_specific:
            agent_config.update(_merge_provider_config(agent_specific, config))
        else:
            agent_config.update(agent_specific)

    return agent_config


def _sanitize_config_for_cache(config: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize configuration by removing sensitive fields before caching
    
    Creates a deep copy and replaces sensitive values with hashes to maintain
    cache key uniqueness while preventing exposure of sensitive data.
    """
    import hashlib
    from copy import deepcopy
    
    sanitized = deepcopy(config)
    
    # List of paths to sensitive fields (nested keys separated by '.')
    sensitive_paths = [
        'openrouter.api_key',
        'claude_code.api_key',  # Future-proofing
        'agents.*.api_key',     # Agent-specific keys
        'agents.*.openrouter.api_key',
        'agents.*.claude_code.api_key'
    ]
    
    def _hash_value(value: str) -> str:
        """Create a deterministic hash of sensitive value"""
        return f"REDACTED_{hashlib.sha256(value.encode()).hexdigest()[:16]}"
    
    def _sanitize_dict(d: Dict[str, Any], path: str = "") -> None:
        """Recursively sanitize dictionary based on sensitive paths"""
        for key, value in list(d.items()):
            current_path = f"{path}.{key}" if path else key
            
            # Check if current path matches any sensitive pattern
            for sensitive_path in sensitive_paths:
                if _path_matches(current_path, sensitive_path):
                    if isinstance(value, str):
                        d[key] = _hash_value(value)
                    break
            
            # Recurse into nested dictionaries
            if isinstance(value, dict):
                _sanitize_dict(value, current_path)
    
    def _path_matches(path: str, pattern: str) -> bool:
        """Check if path matches pattern (supports * wildcard)"""
        pattern_parts = pattern.split('.')
        path_parts = path.split('.')
        
        if len(path_parts) != len(pattern_parts):
            return False
            
        for path_part, pattern_part in zip(path_parts, pattern_parts):
            if pattern_part != '*' and path_part != pattern_part:
                return False
        return True
    
    _sanitize_dict(sanitized)
    return sanitized


def get_agent_config(config: Dict[str, Any], agent_id: Optional[str] = None) -> Dict[str, Any]:
    """Get configuration for specific agent with inheritance (with LRU caching)

    Priority: agent_specific > global > defaults
    
    This wrapper uses LRU cache for performance optimization.
    """
    global _cache_generation, _agent_config_cache
    
    # Create cache key from sanitized config to prevent sensitive data exposure
    sanitized_config = _sanitize_config_for_cache(config)
    config_str = json.dumps(sanitized_config, sort_keys=True)
    cache_key = f"{config_str}:{agent_id or ''}:{_cache_generation}"
    
    # Check cache with thread safety
    with _cache_lock:
        if cache_key in _agent_config_cache:
            return _agent_config_cache[cache_key].copy()
        
        # Compute configuration
        result = _compute_agent_config(config, agent_id)
        
        # Store in cache with size limit
        if len(_agent_config_cache) >= _cache_max_size:
            # Remove oldest entry (simple FIFO for now)
            oldest_key = next(iter(_agent_config_cache))
            del _agent_config_cache[oldest_key]
        
        _agent_config_cache[cache_key] = result
        return result.copy()


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

def validate_numeric_bounds(config: Dict[str, Any], path: str = "") -> List[str]:
    """Validate numeric configuration values are within acceptable bounds
    
    Recursively checks all numeric values in the configuration against
    defined bounds in NUMERIC_BOUNDS.
    
    Parameters
    ----------
    config : dict
        Configuration dictionary to validate
    path : str
        Current path in the configuration tree (for error messages)
        
    Returns
    -------
    List[str]
        List of error messages for out-of-bounds values
    """
    errors = []
    
    for key, value in config.items():
        current_path = f"{path}.{key}" if path else key
        
        if isinstance(value, dict):
            # Recursively validate nested dictionaries
            errors.extend(validate_numeric_bounds(value, current_path))
        elif isinstance(value, (int, float)) and key in NUMERIC_BOUNDS:
            min_val, max_val = NUMERIC_BOUNDS[key]
            if not min_val <= value <= max_val:
                errors.append(
                    f"{current_path}: {value} is outside bounds [{min_val}, {max_val}]"
                )
    
    return errors


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
    
    # Add numeric bounds checking
    bound_errors = validate_numeric_bounds(config)
    if bound_errors:
        raise ValueError("Configuration bounds errors:\n" + "\n".join(bound_errors))

    return True

def invalidate_config_cache():
    """Invalidate all configuration caches"""
    global _cache_generation, _agent_config_cache
    with _cache_lock:
        _cache_generation += 1
        _agent_config_cache.clear()


def clear_config_cache():
    """Clear the configuration cache (useful for testing)"""
    with _cache_lock:
        _config_cache.clear()
    # Also clear LRU cache
    invalidate_config_cache()