import os
import importlib
import json
import hashlib
from typing import Dict, List, Optional, Any
from .base_tool import BaseTool
from exceptions import ToolNotFoundError

# Dynamically populated __all__ for static analysis / IDEs
__all__: list[str] = []

# Module-level cache for discovered tools
_tool_cache: Optional[Dict[str, BaseTool]] = None
_cache_config_hash: Optional[str] = None


def _get_config_hash(config: dict) -> str:
    """Generate a hash of the config to detect changes.
    
    Parameters
    ----------
    config : dict
        Configuration dictionary to hash
        
    Returns
    -------
    str
        MD5 hash of the sorted JSON representation
    """
    config_str = json.dumps(config, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()


def clear_tools_cache() -> None:
    """Clear the tool discovery cache.
    
    Useful for testing or when tools have been modified and need
    to be reloaded.
    """
    global _tool_cache, _cache_config_hash
    _tool_cache = None
    _cache_config_hash = None


def discover_tools(config: dict = None, silent: bool = False) -> Dict[str, BaseTool]:
    """Automatically discover and load all tools from the tools directory.
    
    Scans the tools directory for Python files containing classes that inherit
    from BaseTool. Uses caching to avoid re-discovery when config hasn't changed.
    
    Parameters
    ----------
    config : dict, optional
        Configuration dictionary passed to tool constructors.
        Also used to determine if caching is enabled.
    silent : bool, optional
        Whether to suppress tool loading messages (default: False)
        
    Returns
    -------
    Dict[str, BaseTool]
        Dictionary mapping tool names to instantiated tool objects
        
    Notes
    -----
    - Excludes __init__.py and base_tool.py from scanning
    - Caching can be disabled via config['performance']['cache_tool_discovery']
    - Failed tool imports are logged but don't stop the discovery process
    
    Examples
    --------
    >>> tools = discover_tools({'search': {'max_results': 10}})
    >>> calculator = tools['calculate']
    >>> result = calculator.execute(expression="2+2")
    """
    global _tool_cache, _cache_config_hash
    
    # Check if caching is enabled
    if config and config.get('performance', {}).get('cache_tool_discovery', True):
        current_hash = _get_config_hash(config or {})
        
        # Return cached tools if config hasn't changed
        if _tool_cache is not None and _cache_config_hash == current_hash:
            if not silent:
                print("Using cached tool discovery")
            return _tool_cache
    
    # If we get here, we need to discover tools
    tools = {}

    # Get the tools directory path
    tools_dir = os.path.dirname(__file__)

    # Scan for Python files (excluding __init__.py and base_tool.py)
    for filename in os.listdir(tools_dir):
        if filename.endswith(".py") and filename not in ["__init__.py", "base_tool.py"]:
            module_name = filename[:-3]  # Remove .py extension

            try:
                # Import the module
                module = importlib.import_module(f".{module_name}", package="tools")

                # Find tool classes that inherit from BaseTool
                for item_name in dir(module):
                    item = getattr(module, item_name)
                    if (
                        isinstance(item, type)
                        and issubclass(item, BaseTool)
                        and item != BaseTool
                    ):
                        # Instantiate the tool
                        tool_instance = item(config or {})
                        tools[tool_instance.name] = tool_instance
                        __all__.append(tool_instance.name)
                        if not silent:
                            print(f"Loaded tool: {tool_instance.name}")

            except Exception as e:
                if not silent:
                    print(f"Warning: Could not load tool from {filename}: {e}")

    # Update cache if caching is enabled
    if config and config.get('performance', {}).get('cache_tool_discovery', True):
        _tool_cache = tools
        _cache_config_hash = _get_config_hash(config or {})
        if not silent:
            print(f"Cached {len(tools)} tools for future use")
    
    return tools


def __getattr__(name):
    try:
        return discover_tools()[name]
    except KeyError:
        raise ToolNotFoundError(name)
