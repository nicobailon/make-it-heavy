import json
import yaml
import threading
import logging
from collections import OrderedDict
from openai import OpenAI
from tools import discover_tools
from exceptions import OpenRouterError
from config_utils import get_agent_config

# Set up logging
logger = logging.getLogger(__name__)

# Cache for Claude Code module import
_claude_code_module = None
_claude_code_import_error = None

# Cache for configuration keys to avoid repeated hashing
_config_key_cache = {}
_config_key_cache_lock = threading.Lock()


def _get_claude_code_agent_class():
    """Lazy load and cache ClaudeCodeCLIAgent class
    
    Returns:
        ClaudeCodeCLIAgent: The cached agent class
        
    Raises:
        ImportError: If the module cannot be imported
    """
    global _claude_code_module, _claude_code_import_error
    
    if _claude_code_module is not None:
        return _claude_code_module.ClaudeCodeCLIAgent
    
    if _claude_code_import_error is not None:
        raise _claude_code_import_error
    
    try:
        import claude_code_cli_provider
        _claude_code_module = claude_code_cli_provider
        return claude_code_cli_provider.ClaudeCodeCLIAgent
    except ImportError as e:
        _claude_code_import_error = ImportError(
            f"Failed to import Claude Code provider: {e}\n"
            "Ensure claude_code_cli_provider.py is in the correct location."
        )
        raise _claude_code_import_error


class AgentPool:
    """Pool for reusing agent instances to improve performance
    
    Agents are stored by configuration key to ensure compatibility.
    The pool has a maximum size to prevent unbounded memory usage.
    Uses OrderedDict for O(1) lookup and LRU eviction.
    """
    def __init__(self, max_size: int = 10):
        """Initialize the agent pool
        
        Parameters
        ----------
        max_size : int
            Maximum number of agents to keep in the pool
        """
        self.max_size = max_size
        self.lock = threading.Lock()
        self.stats = {'hits': 0, 'misses': 0, 'evictions': 0}
        # Dictionary mapping config_key -> list of agents
        self.agents_by_config = {}
        # OrderedDict for LRU eviction order: agent_id -> (config_key, agent)
        # Using id(agent) as key for O(1) removal
        self.eviction_order = OrderedDict()
        self.current_size = 0
    
    def get_agent(self, config_key: str, factory_func):
        """Get agent from pool or create new one
        
        Parameters
        ----------
        config_key : str
            Unique key representing the agent configuration
        factory_func : callable
            Function to create a new agent if needed
            
        Returns
        -------
        Agent instance
        """
        with self.lock:
            # O(1) lookup for matching config
            if config_key in self.agents_by_config and self.agents_by_config[config_key]:
                # Pop agent from the list
                agent = self.agents_by_config[config_key].pop()
                if not self.agents_by_config[config_key]:
                    # Remove empty list
                    del self.agents_by_config[config_key]
                
                # O(1) removal from eviction order
                agent_id = id(agent)
                if agent_id in self.eviction_order:
                    del self.eviction_order[agent_id]
                self.current_size -= 1
                
                self.stats['hits'] += 1
                return agent
            
            # Create new agent
            self.stats['misses'] += 1
            return factory_func()
    
    def return_agent(self, agent, config_key: str):
        """Return agent to pool for reuse
        
        Parameters
        ----------
        agent : Agent
            The agent instance to return
        config_key : str
            Configuration key for this agent
        """
        # Clean up agent state if it has a cleanup method
        if hasattr(agent, 'cleanup'):
            try:
                agent.cleanup()
            except Exception as e:
                logger.warning(f"Error during agent cleanup: {e}")
        
        try:
            with self.lock:
                # Check if pool is full
                if self.current_size >= self.max_size:
                    # Evict oldest agent (LRU) - O(1) operation with OrderedDict
                    if self.eviction_order:
                        try:
                            # popitem(last=False) removes the oldest item (FIFO/LRU)
                            old_agent_id, (old_key, old_agent) = self.eviction_order.popitem(last=False)
                            
                            # Remove from agents_by_config
                            if old_key in self.agents_by_config:
                                try:
                                    self.agents_by_config[old_key].remove(old_agent)
                                    if not self.agents_by_config[old_key]:
                                        del self.agents_by_config[old_key]
                                except ValueError:
                                    # Agent already removed, this is fine
                                    pass
                            
                            self.current_size -= 1
                            self.stats['evictions'] += 1
                            
                            # Try to clean up the evicted agent
                            if hasattr(old_agent, 'cleanup'):
                                try:
                                    old_agent.cleanup()
                                except Exception as e:
                                    logger.warning(f"Error cleaning up evicted agent: {e}")
                        except (KeyError, ValueError) as e:
                            logger.error(f"Pool consistency error during eviction: {e}")
                            # Continue anyway to avoid losing the new agent
                    else:
                        # Pool full and no agents to evict
                        logger.warning(
                            f"Agent pool is full (max_size={self.max_size}). "
                            f"Agent for config_key={config_key} will be discarded. "
                            f"Consider increasing pool size if this happens frequently."
                        )
                        self.stats['evictions'] += 1
                        return
                
                # Add agent to pool
                try:
                    if config_key not in self.agents_by_config:
                        self.agents_by_config[config_key] = []
                    self.agents_by_config[config_key].append(agent)
                    
                    # Add to eviction order - O(1) operation
                    agent_id = id(agent)
                    self.eviction_order[agent_id] = (config_key, agent)
                    self.current_size += 1
                except Exception as e:
                    logger.error(f"Failed to add agent to pool: {e}")
                    raise
        except Exception as e:
            logger.error(f"Critical error in agent pool return operation: {e}")
            # Even if pool operation fails, we don't want to leak the agent
            # Let it be garbage collected
            self.stats['evictions'] += 1
    
    def get_stats(self):
        """Get pool statistics
        
        Returns
        -------
        dict
            Dictionary with hits, misses, and evictions counts
        """
        with self.lock:
            return self.stats.copy()


# Global agent pool
_agent_pool = AgentPool()


def _get_config_key(provider: str, agent_id: str, agent_config: dict) -> str:
    """Generate a lightweight configuration key for agent pooling
    
    Only includes fields that affect agent behavior, not metadata.
    Uses caching to avoid repeated hashing.
    """
    # Create cache key from provider and agent_id
    cache_key = f"{provider}:{agent_id or 'default'}"
    
    with _config_key_cache_lock:
        # First check if we have a cached result
        if cache_key in _config_key_cache:
            cached_config, cached_hash = _config_key_cache[cache_key]
            
            # Extract only essential fields that affect behavior
            essential_fields = (
                agent_config.get('model'),
                agent_config.get('temperature'),
                agent_config.get('system_prompt'),
                agent_config.get('max_iterations'),
                agent_config.get('tools', {}).get('enabled')
            )
            
            if cached_config == essential_fields:
                return cached_hash
        
        # Extract essential fields as tuple (hashable and faster to compare)
        essential_fields = (
            agent_config.get('model'),
            agent_config.get('temperature'),
            agent_config.get('system_prompt'),
            agent_config.get('max_iterations'),
            agent_config.get('tools', {}).get('enabled')
        )
        
        # Use Python's built-in hash() for much faster hashing
        # Convert to string for consistent hash across runs
        config_hash = str(abs(hash(essential_fields)))[:8]
        
        full_key = f"{provider}:{agent_id or 'default'}:{config_hash}"
        
        # Cache the result
        _config_key_cache[cache_key] = (essential_fields, full_key)
        
        return full_key


class OpenRouterAgent:
    """Agent that uses OpenRouter API for AI-powered task execution.
    
    Implements an agentic loop that continues until task completion or
    max iterations reached. Supports tool usage through OpenAI function calling.
    
    Attributes:
        config (dict): Configuration loaded from YAML
        client (OpenAI): OpenRouter API client
        tools (list): OpenAI-formatted tool definitions
        tool_mapping (dict): Maps tool names to execution functions
        silent (bool): Whether to suppress debug output
    """
    
    def __init__(self, config_path="config.yaml", client=None, silent=False, agent_config=None, config=None):
        """Initialize OpenRouter agent with optional agent-specific configuration.
        
        Parameters
        ----------
        config_path : str, optional
            Path to configuration YAML file (default: "config.yaml")
        client : OpenAI, optional
            Pre-configured OpenAI client. If None, creates one from config.
        silent : bool, optional
            Whether to suppress debug output (default: False)
        agent_config : dict, optional
            Pre-loaded agent-specific configuration. If None, uses global config.
        config : dict, optional
            Pre-loaded full configuration. If provided, skips YAML loading.
            
        Raises
        ------
        OpenRouterError
            If API initialization fails
        """
        # Load configuration only if not provided
        if config is None:
            with open(config_path, "r") as f:
                self.config = yaml.safe_load(f)
        else:
            self.config = config
            
        if agent_config is None:
            # Legacy behavior - use global configuration
            agent_config = get_agent_config(self.config)
        
        self.agent_config = agent_config
        self.silent = silent

        # Use agent-specific configuration for client
        self.client = client or OpenAI(
            base_url=agent_config.get("base_url", self.config["openrouter"]["base_url"]),
            api_key=agent_config.get("api_key", self.config["openrouter"]["api_key"]),
        )

        # Discover tools dynamically
        self.discovered_tools = discover_tools(self.config, silent=self.silent)

        # Build OpenRouter tools array
        self.tools = [
            tool.to_openrouter_schema() for tool in self.discovered_tools.values()
        ]

        # Build tool mapping
        self.tool_mapping = {
            name: tool.execute for name, tool in self.discovered_tools.items()
        }

    def call_llm(self, messages):
        """Make OpenRouter API call with tools.
        
        Parameters
        ----------
        messages : list
            Conversation history in OpenAI message format
            
        Returns
        -------
        OpenAI response object
            Contains choices with message content and tool calls
            
        Raises
        ------
        OpenRouterError
            Wraps any API errors with context
        """
        try:
            response = self.client.chat.completions.create(
                model=self.agent_config.get("model", self.config["openrouter"]["model"]),
                messages=messages,
                tools=self.tools,
            )
            return response
        except Exception as e:
            # Wrap in our custom exception
            raise OpenRouterError(message=f"LLM call failed: {str(e)}")

    def handle_tool_call(self, tool_call):
        """Handle a tool call and return the result message.
        
        Parameters
        ----------
        tool_call : OpenAI tool call object
            Contains function name and arguments
            
        Returns
        -------
        dict
            Tool result message in OpenAI format with:
            - role: "tool"
            - tool_call_id: ID from the tool call
            - name: Tool name
            - content: JSON-encoded result or error
        """
        try:
            # Extract tool name and arguments
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)

            # Call appropriate tool from tool_mapping
            if tool_name in self.tool_mapping:
                tool_result = self.tool_mapping[tool_name](**tool_args)
            else:
                tool_result = {"error": f"Unknown tool: {tool_name}"}

            # Return tool result message
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": json.dumps(tool_result),
            }

        except Exception as e:
            return {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": tool_name,
                "content": json.dumps({"error": f"Tool execution failed: {str(e)}"}),
            }

    def run(self, user_input: str) -> str:
        """Run the agent with user input and return full conversation content.
        
        Implements the agentic loop, continuing until task completion tool
        is called or max iterations reached.
        
        Parameters
        ----------
        user_input : str
            The user's request or prompt
            
        Returns
        -------
        str
            Combined content from all assistant messages
            
        Examples
        --------
        >>> agent = OpenRouterAgent(silent=True)
        >>> response = agent.run("Search for Python tutorials")
        >>> print(response)
        "I found several Python tutorials..."
        """
        # Initialize messages with system prompt and user input
        messages = [
            {"role": "system", "content": self.agent_config.get("system_prompt", self.config.get("system_prompt", ""))},
            {"role": "user", "content": user_input},
        ]

        # Track all assistant responses for full content capture
        full_response_content = []

        # Implement agentic loop from OpenRouter docs
        max_iterations = self.agent_config.get("max_iterations", self.config.get("agent", {}).get("max_iterations", 10))
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            if not self.silent:
                print(f"🔄 Agent iteration {iteration}/{max_iterations}")

            # Call LLM
            response = self.call_llm(messages)

            # Add the response to messages
            assistant_message = response.choices[0].message
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_message.content,
                    "tool_calls": assistant_message.tool_calls,
                }
            )

            # Capture assistant content for full response
            if assistant_message.content:
                full_response_content.append(assistant_message.content)

            # Check if there are tool calls
            if assistant_message.tool_calls:
                if not self.silent:
                    print(
                        f"🔧 Agent making {len(assistant_message.tool_calls)} tool call(s)"
                    )
                # Handle each tool call
                task_completed = False
                for tool_call in assistant_message.tool_calls:
                    if not self.silent:
                        print(f"   📞 Calling tool: {tool_call.function.name}")
                    tool_result = self.handle_tool_call(tool_call)
                    messages.append(tool_result)

                    # Check if this was the task completion tool
                    if tool_call.function.name == "mark_task_complete":
                        task_completed = True
                        if not self.silent:
                            print("✅ Task completion tool called - exiting loop")
                        # Return FULL conversation content, not just completion message
                        return "\n\n".join(full_response_content)

                # If task was completed, we already returned above
                if task_completed:
                    return "\n\n".join(full_response_content)
            else:
                if not self.silent:
                    print("💭 Agent responded without tool calls - continuing loop")

            # Continue the loop regardless of whether there were tool calls or not

        # If max iterations reached, return whatever content we gathered
        return (
            "\n\n".join(full_response_content)
            if full_response_content
            else "Maximum iterations reached. The agent may be stuck in a loop."
        )


# Store original function for backward compatibility
def _create_agent_original(config_path="config.yaml", silent=False, client=None):
    """Original factory function - kept for backward compatibility"""
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    provider = config.get("provider", "openrouter")

    if provider == "claude_code":
        ClaudeCodeCLIAgent = _get_claude_code_agent_class()
        return ClaudeCodeCLIAgent(config_path, silent)
    else:
        return OpenRouterAgent(config_path, client=client, silent=silent)


def create_agent(config_path="config.yaml", agent_id=None, silent=False, client=None, preloaded_config=None, use_pool=True):
    """Enhanced factory function with agent-specific configuration support and pooling

    Args:
        config_path: Path to configuration file
        agent_id: Optional agent identifier for agent-specific config
        silent: If True, suppresses debug output
        client: Optional OpenAI client for dependency injection
        preloaded_config: Optional pre-loaded configuration dict
        use_pool: If True, uses agent pooling for performance (default: True)

    Returns:
        Agent instance configured for specific agent or with global settings
    """
    from config_utils import load_config, validate_config, get_agent_config
    
    # Load configuration if not provided
    if preloaded_config is None:
        config = load_config(config_path)
        validate_config(config)
    else:
        config = preloaded_config

    # Get agent-specific configuration
    agent_config = get_agent_config(config, agent_id)
    provider = agent_config['provider']
    
    # Generate configuration key for pooling (optimized)
    config_key = _get_config_key(provider, agent_id, agent_config)
    
    def factory():
        """Factory function to create new agent"""
        if provider == "claude_code":
            ClaudeCodeCLIAgent = _get_claude_code_agent_class()
            return ClaudeCodeCLIAgent(
                config_path=config_path,
                silent=silent,
                agent_config=agent_config
            )
        else:
            return OpenRouterAgent(
                config_path=config_path,
                client=client,
                silent=silent,
                agent_config=agent_config,
                config=config
            )
    
    # Use pool if enabled
    if use_pool:
        return _agent_pool.get_agent(config_key, factory)
    else:
        return factory()


# Backward compatibility wrappers
def create_agent_legacy(config_path="config.yaml", silent=False, client=None):
    """Legacy agent creation for backward compatibility"""
    return create_agent(config_path=config_path, silent=silent, client=client)


# Alias for consistency with documentation
create_agent_original = _create_agent_original
