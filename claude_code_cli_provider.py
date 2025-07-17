import json
import subprocess
import yaml
import os
import sys
import time
from typing import Dict, Any, List, Optional
from tools import discover_tools
from constants import (
    DEFAULT_CLI_VERIFICATION_TIMEOUT,
    DEFAULT_PROGRESS_UPDATE_INTERVAL,
    DEFAULT_PREVIEW_LINES,
    DEFAULT_PREVIEW_DISPLAY_LINES,
    DEFAULT_LINE_TRUNCATE_LENGTH,
    DEFAULT_JSON_PREVIEW_LENGTH,
    DEFAULT_MAX_PROMPT_SIZE
)
from exceptions import (
    CLINotFoundError,
    CLIVerificationError,
    StreamingParseError
)

# Module-level cache for system prompts
_prompt_cache: Dict[str, str] = {}


class ClaudeCodeCLIAgent:
    """Agent that interfaces with Claude Code CLI for AI-powered task execution.
    
    This agent uses the Claude Code CLI to execute tasks with access to custom tools
    through a Python bridge script. It handles streaming JSON output from the CLI
    and manages the conversation flow until task completion.
    
    Attributes:
        config (dict): Configuration loaded from YAML file
        silent (bool): Whether to suppress debug output
        discovered_tools (dict): Dynamically discovered tool instances
        system_prompt (str): Enhanced prompt with tool instructions
    """
    
    def __init__(self, config_path="config.yaml", silent=False):
        """Initialize Claude Code CLI agent.
        
        Parameters
        ----------
        config_path : str, optional
            Path to configuration YAML file (default: "config.yaml")
        silent : bool, optional
            Whether to suppress debug output (default: False)
            
        Raises
        ------
        CLINotFoundError
            If Claude Code CLI is not installed
        CLIVerificationError
            If CLI verification fails
        """
        init_start = time.time()
        # Load configuration
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Silent mode for orchestrator (suppresses debug output)
        self.silent = silent
        self.timing_enabled = os.environ.get('TIMING_DEBUG', 'false').lower() == 'true'
        
        # Discover tools dynamically (for compatibility check)
        tool_start = time.time()
        self.discovered_tools = discover_tools(self.config, silent=self.silent)
        if self.timing_enabled:
            print(f"⏱️  Tool discovery took: {time.time() - tool_start:.2f}s")
        
        # Build tool mapping (kept for interface compatibility)
        self.tool_mapping = {name: tool.execute for name, tool in self.discovered_tools.items()}
        
        # Add tools attribute for orchestrator compatibility
        self.tools = []  # Claude Code doesn't use OpenAI-style tools
        
        # Get Claude Code specific config
        self.claude_config = self.config.get('claude_code', {})
        
        # Get max iterations from config
        self.max_iterations = self.config.get('agent', {}).get('max_iterations', 10)
        
        # Get base system prompt
        self.base_system_prompt = self.config.get('system_prompt', '')
        
        # Build enhanced system prompt with tool instructions (with caching)
        prompt_start = time.time()
        self.system_prompt = self._get_or_build_system_prompt()
        if self.timing_enabled:
            print(f"⏱️  System prompt building took: {time.time() - prompt_start:.2f}s")
            print(f"⏱️  System prompt size: {len(self.system_prompt)} chars")
        
        # Get CLI path (default to 'claude' if not specified)
        self.cli_path = self.claude_config.get('cli_path', 'claude')
        
        # Verify Claude CLI is installed
        verify_start = time.time()
        self._verify_cli_installed()
        if self.timing_enabled:
            print(f"⏱️  CLI verification took: {time.time() - verify_start:.2f}s")
            print(f"⏱️  Total init time: {time.time() - init_start:.2f}s")
        
        # Debug: Print system prompt preview only in debug mode
        if os.environ.get('DEBUG_CLAUDE_CLI'):
            preview_lines = self.config.get('display', {}).get('preview_lines', DEFAULT_PREVIEW_LINES)
            display_lines = self.config.get('display', {}).get('preview_display_lines', DEFAULT_PREVIEW_DISPLAY_LINES)
            truncate_length = self.config.get('display', {}).get('line_truncate_length', DEFAULT_LINE_TRUNCATE_LENGTH)
            
            lines = self.system_prompt.split('\n')[:preview_lines]
            print("📋 System prompt preview:")
            for line in lines[:display_lines]:
                print(f"   {line[:truncate_length]}..." if len(line) > truncate_length else f"   {line}")
            print(f"   ... ({len(self.system_prompt)} total characters)")
    
    def _verify_cli_installed(self):
        """Verify Claude CLI is installed and accessible"""
        try:
            # Run claude --help to check if CLI is installed
            result = subprocess.run(
                [self.cli_path, '--help'],
                capture_output=True,
                text=True,
                timeout=self.config.get('timeouts', {}).get('cli_verification', DEFAULT_CLI_VERIFICATION_TIMEOUT)
            )
            
            if result.returncode != 0:
                raise CLIVerificationError(f"Claude CLI returned error: {result.stderr}")
            
            if not self.silent:
                print("✓ Claude CLI verified")
                
        except FileNotFoundError:
            raise CLINotFoundError(self.cli_path)
        except subprocess.TimeoutExpired:
            raise CLIVerificationError("Claude CLI verification timed out")
        except CLIVerificationError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            raise CLIVerificationError(f"Failed to verify Claude CLI: {e}")
    
    def _get_or_build_system_prompt(self) -> str:
        """Get system prompt from cache or build it.
        
        Uses caching to avoid rebuilding the prompt on every initialization
        when tools haven't changed.
        
        Returns
        -------
        str
            The complete system prompt with tool instructions
        """
        global _prompt_cache
        
        # Check if caching is enabled
        if self.config.get('performance', {}).get('cache_system_prompts', True):
            # Create cache key based on tools and base prompt
            cache_key = f"{self.base_system_prompt}_{sorted(self.discovered_tools.keys())}"
            cache_hash = str(hash(cache_key))
            
            if cache_hash in _prompt_cache:
                if not self.silent:
                    print("Using cached system prompt")
                return _prompt_cache[cache_hash]
            
            # Build and cache the prompt
            prompt = self._build_enhanced_system_prompt()
            _prompt_cache[cache_hash] = prompt
            return prompt
        else:
            # Caching disabled, build fresh
            return self._build_enhanced_system_prompt()
    
    def _build_enhanced_system_prompt(self) -> str:
        """Build system prompt with instructions for using custom tools.
        
        Constructs a comprehensive prompt that includes the base system prompt
        plus detailed instructions and examples for each discovered tool.
        
        Returns
        -------
        str
            Enhanced system prompt, potentially truncated if too large
        """
        prompt_parts = [self.base_system_prompt]
        
        # Add clear instructions about tool usage
        prompt_parts.append("\n\n## IMPORTANT: Tool Usage Instructions")
        prompt_parts.append("You have access to custom tools through a Python bridge script.")
        prompt_parts.append("To use ANY of the custom tools listed below, you MUST:")
        prompt_parts.append("1. Use the Bash tool")
        prompt_parts.append("2. Run the command: python use_tool.py <tool_name> '<args>...</args>'")
        prompt_parts.append("")
        prompt_parts.append("CRITICAL: Use XML format wrapped in single quotes to avoid JSON escaping issues.")
        prompt_parts.append("The XML format is simple: <args><param>value</param></args>")
        prompt_parts.append("DO NOT try to use tools directly - they are only accessible through the use_tool.py bridge.")
        prompt_parts.append("")
        
        # Add instructions for using the tool bridge
        prompt_parts.append("## Available Custom Tools")
        
        # List available tools with specific examples
        for tool_name, tool in self.discovered_tools.items():
            prompt_parts.append(f"\n### {tool_name}")
            prompt_parts.append(f"Description: {tool.description}")
            
            # Provide concrete examples for each tool
            if tool_name == "search_web":
                prompt_parts.append("Example usage:")
                prompt_parts.append("```bash")
                prompt_parts.append("python use_tool.py search_web '<args><query>latest AI news</query><max_results>5</max_results></args>'")
                prompt_parts.append("```")
            elif tool_name == "calculate":
                prompt_parts.append("Example usage:")
                prompt_parts.append("```bash")
                prompt_parts.append("python use_tool.py calculate '<args><expression>2 + 2 * 3</expression></args>'")
                prompt_parts.append("```")
            elif tool_name == "read_file":
                prompt_parts.append("Example usage:")
                prompt_parts.append("```bash")
                prompt_parts.append("python use_tool.py read_file '<args><path>example.txt</path></args>'")
                prompt_parts.append("```")
            elif tool_name == "write_file":
                prompt_parts.append("Example usage:")
                prompt_parts.append("```bash")
                prompt_parts.append("python use_tool.py write_file '<args><path>output.txt</path><content>Hello World</content></args>'")
                prompt_parts.append("```")
            elif tool_name == "mark_task_complete":
                prompt_parts.append("Example usage:")
                prompt_parts.append("```bash")
                prompt_parts.append("python use_tool.py mark_task_complete '<args><task_summary>Calculated 2+2</task_summary><completion_message>The answer is 4</completion_message></args>'")
                prompt_parts.append("```")
        
        # Final reminder
        prompt_parts.append("\n## Task Completion")
        prompt_parts.append("IMPORTANT: When you have fully completed the user's request, you MUST use the Bash tool to run:")
        prompt_parts.append("python use_tool.py mark_task_complete '<args><task_summary>brief summary</task_summary><completion_message>final message</completion_message></args>'")
        prompt_parts.append("This signals that the task is finished and stops the iteration loop.")
        
        # Build final prompt and check size
        final_prompt = "\n".join(prompt_parts)
        max_prompt_size = self.config.get('display', {}).get('max_prompt_size', DEFAULT_MAX_PROMPT_SIZE)
        
        if len(final_prompt) > max_prompt_size:
            if not self.silent:
                print(f"⚠️ System prompt size ({len(final_prompt)} chars) exceeds limit ({max_prompt_size} chars)")
            # Truncate with warning message
            final_prompt = final_prompt[:max_prompt_size - 100] + "\n\n[Prompt truncated due to size limit]"
        
        return final_prompt
    
    def _handle_system_message(self, message: Dict[str, Any]) -> None:
        """Handle system initialization messages."""
        if not self.silent and message.get('subtype') == 'init':
            print(f"🤖 Using Claude Code CLI with model: {message.get('model', 'default')}")
            print(f"📂 Working directory: {message.get('cwd', 'unknown')}")
    
    def _handle_assistant_message(self, message: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Handle assistant messages. Returns True if task completed."""
        assistant_msg = message.get('message', {})
        task_completed = False
        
        # Count iterations
        context['iteration_count'] += 1
        current_time = time.time()
        
        if not self.silent:
            elapsed = current_time - context['parse_start']
            print(f"🔄 Claude Code turn {context['iteration_count']}/{self.max_iterations} (elapsed: {elapsed:.1f}s)")
        
        # Progress updates
        update_interval = self.config.get('timeouts', {}).get('progress_update_interval', DEFAULT_PROGRESS_UPDATE_INTERVAL)
        if self.timing_enabled and current_time - context['last_update'] > update_interval:
            print(f"⏱️  Still processing... {current_time - context['parse_start']:.1f}s elapsed")
            context['last_update'] = current_time
        
        # Process content blocks
        for content_block in assistant_msg.get('content', []):
            if content_block.get('type') == 'text':
                text = content_block.get('text', '')
                if text:
                    context['full_response_content'].append(text)
            
            elif content_block.get('type') == 'tool_use':
                tool_name = content_block.get('name', '')
                if not self.silent:
                    print(f"   📞 Claude Code using tool: {tool_name}")
                
                # Check for task completion
                if tool_name == 'Bash':
                    tool_input = content_block.get('input', {})
                    command = tool_input.get('command', '')
                    if 'use_tool.py' in command and 'mark_task_complete' in command:
                        task_completed = True
                        if not self.silent:
                            print("✅ Task completion tool called")
        
        return task_completed
    
    def _handle_result_message(self, message: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Handle final result messages."""
        if message.get('subtype') == 'success':
            result_text = message.get('result', '')
            if result_text and result_text not in context['full_response_content']:
                context['full_response_content'].append(result_text)
        
        # Track cost
        if 'total_cost_usd' in message:
            context['total_cost'] = message['total_cost_usd']
            if not self.silent and context['total_cost'] > 0:
                print(f"💰 Cost: ${context['total_cost']:.4f}")
        
        # Handle errors
        if message.get('is_error'):
            error_subtype = message.get('subtype', 'unknown_error')
            if error_subtype == 'error_max_turns':
                if not self.silent:
                    print("⚠️ Maximum turns reached")
            else:
                if not self.silent:
                    print(f"❌ Error: {error_subtype}")
    
    def _parse_streaming_json(self, process: subprocess.Popen) -> str:
        """Parse streaming JSON output from Claude Code CLI"""
        # Initialize parsing context
        context = {
            'full_response_content': [],
            'task_completed': False,
            'iteration_count': 0,
            'total_cost': 0.0,
            'parse_start': time.time(),
            'last_update': time.time()
        }
        
        try:
            for line in process.stdout:
                line = line.decode('utf-8').strip()
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    message_type = message.get('type')
                    
                    # Route to appropriate handler
                    if message_type == 'system':
                        self._handle_system_message(message)
                    
                    elif message_type == 'assistant':
                        task_completed = self._handle_assistant_message(message, context)
                        if task_completed:
                            context['task_completed'] = True
                    
                    elif message_type == 'user':
                        # Tool results come back as user messages
                        pass
                    
                    elif message_type == 'result':
                        self._handle_result_message(message, context)
                
                except json.JSONDecodeError as e:
                    if not self.silent:
                        json_preview = self.config.get('display', {}).get('json_preview_length', DEFAULT_JSON_PREVIEW_LENGTH)
                        print(f"⚠️ Failed to parse JSON: {line[:json_preview]}...")
                    # Log but continue processing
                    continue
        
        except Exception as e:
            if not self.silent:
                print(f"❌ Error reading output: {e}")
        
        # Read any errors
        stderr_output = process.stderr.read().decode('utf-8').strip()
        if stderr_output and not self.silent:
            print(f"❌ CLI Error: {stderr_output}")
        
        # Return combined content from all assistant messages
        full_response_content = context['full_response_content']
        return "\n\n".join(full_response_content) if full_response_content else "No response generated"
    
    def run(self, user_input: str) -> str:
        """Run the agent with user input and return full conversation content.
        
        Executes the Claude Code CLI with the given prompt and custom tool access.
        Continues running until the task is marked complete or max iterations reached.
        
        Parameters
        ----------
        user_input : str
            The user's request or prompt
            
        Returns
        -------
        str
            Combined response content from all assistant messages
            
        Raises
        ------
        subprocess.TimeoutExpired
            If the CLI process exceeds configured timeout
        StreamingParseError
            If JSON parsing fails during streaming
            
        Examples
        --------
        >>> agent = ClaudeCodeCLIAgent(silent=True)
        >>> response = agent.run("Calculate 2+2 and explain the result")
        >>> print(response)
        "The answer is 4. This is basic arithmetic..."
        """
        run_start = time.time()
        if not self.silent:
            print(f"🤖 Using Claude Code CLI provider")
            if self.timing_enabled:
                print(f"⏱️  Input: {user_input[:50]}..." if len(user_input) > 50 else f"⏱️  Input: {user_input}")
        
        # Build command
        cmd = [
            self.cli_path,
            '-p', user_input,  # Print mode with prompt
            '--output-format', 'stream-json',  # Streaming JSON for parsing
            '--verbose',  # Required for stream-json output
            '--system-prompt', self.system_prompt,
            '--max-turns', str(self.max_iterations),
            '--allowedTools', 'Bash(python use_tool.py *)'
        ]
        
        # Add model if specified
        if 'model' in self.claude_config:
            cmd.extend(['--model', self.claude_config['model']])
        
        # Set working directory to project root
        cwd = os.path.dirname(os.path.abspath(__file__))
        
        try:
            # Run subprocess
            if self.timing_enabled:
                print(f"⏱️  Starting Claude CLI subprocess...")
            subprocess_start = time.time()
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=cwd,
                text=False  # We'll decode manually for better control
            )
            
            if self.timing_enabled:
                print(f"⏱️  Subprocess started in {time.time() - subprocess_start:.2f}s")
            
            # Parse streaming output
            result = self._parse_streaming_json(process)
            
            # Wait for process to complete
            process.wait()
            
            total_time = time.time() - run_start
            if self.timing_enabled:
                print(f"⏱️  Total execution time: {total_time:.2f}s")
            
            if process.returncode != 0 and not self.silent:
                print(f"⚠️ Claude Code CLI exited with code: {process.returncode}")
            
            return result
            
        except FileNotFoundError:
            error_msg = (
                f"Claude Code CLI not found at '{self.cli_path}'. "
                f"Please install with: npm install -g @anthropic-ai/claude-code"
            )
            if not self.silent:
                print(f"❌ {error_msg}")
            return error_msg
        except Exception as e:
            error_msg = f"Claude Code CLI execution failed: {str(e)}"
            if not self.silent:
                print(f"❌ {error_msg}")
            return error_msg