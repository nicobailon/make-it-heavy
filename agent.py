import json
import yaml
from openai import OpenAI
from tools import discover_tools
from exceptions import OpenRouterError, ProviderError


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
    
    def __init__(self, config_path="config.yaml", client=None, silent=False):
        """Initialize OpenRouter agent.
        
        Parameters
        ----------
        config_path : str, optional
            Path to configuration YAML file (default: "config.yaml")
        client : OpenAI, optional
            Pre-configured OpenAI client. If None, creates one from config.
        silent : bool, optional
            Whether to suppress debug output (default: False)
            
        Raises
        ------
        OpenRouterError
            If API initialization fails
        """
        # Load configuration
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        # Silent mode for orchestrator (suppresses debug output)
        self.silent = silent

        # Dependency injection
        self.client = client or OpenAI(
            base_url=self.config["openrouter"]["base_url"],
            api_key=self.config["openrouter"]["api_key"],
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
                model=self.config["openrouter"]["model"],
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
            {"role": "system", "content": self.config["system_prompt"]},
            {"role": "user", "content": user_input},
        ]

        # Track all assistant responses for full content capture
        full_response_content = []

        # Implement agentic loop from OpenRouter docs
        max_iterations = self.config.get("agent", {}).get("max_iterations", 10)
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


def create_agent(config_path="config.yaml", silent=False, client=None):
    """Factory function to create appropriate agent based on provider config

    Args:
        config_path: Path to configuration file
        silent: If True, suppresses debug output
        client: Optional OpenAI client for dependency injection

    Returns:
        Agent instance (OpenRouterAgent or ClaudeCodeCLIAgent)
    """
    import yaml

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    provider = config.get("provider", "openrouter")

    if provider == "claude_code":
        from claude_code_cli_provider import ClaudeCodeCLIAgent

        return ClaudeCodeCLIAgent(config_path, silent)
    else:
        return OpenRouterAgent(config_path, client=client, silent=silent)
