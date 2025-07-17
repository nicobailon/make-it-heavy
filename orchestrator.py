import json
import time
import threading
import os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Any
from agent import create_agent
from config_utils import get_orchestrator_config, load_config, validate_config
from constants import DEFAULT_TASK_TIMEOUT

class TaskOrchestrator:
    """Orchestrates multiple agents to analyze tasks from different perspectives.
    
    The orchestrator decomposes user queries into specialized sub-questions,
    runs multiple agents in parallel to answer them, and synthesizes the
    results into a comprehensive response.
    
    New Features:
        - Each agent can have its own model, provider, and system prompt
        - Orchestrator can use a dedicated model for question generation and synthesis
        - Thread-safe configuration with caching for performance
    
    Attributes:
        config (dict): Configuration loaded from YAML
        orchestrator_config (dict): Orchestrator-specific configuration with model overrides
        num_agents (int): Number of parallel agents to run
        task_timeout (int): Timeout per agent in seconds
        agent_factory (callable): Factory function to create agents
        agent_progress (dict): Real-time progress tracking per agent
        agent_results (dict): Results storage per agent
    """
    
    def __init__(self, config_path="config.yaml", silent=False, agent_factory=None):
        """Initialize the task orchestrator.
        
        Parameters
        ----------
        config_path : str, optional
            Path to configuration YAML file (default: "config.yaml")
        silent : bool, optional
            Whether to suppress progress output (default: False)
        agent_factory : callable, optional
            Factory function to create agents. If None, uses create_agent.
            Useful for dependency injection in tests.
        """
        # Load and validate configuration
        self.config = load_config(config_path)
        validate_config(self.config)
        
        # Get orchestrator-specific configuration
        self.orchestrator_config = get_orchestrator_config(self.config)
        
        # Standard orchestrator settings with safe defaults
        orch_section = self.config.get('orchestrator', {})
        self.num_agents = orch_section.get('parallel_agents', 4)
        self.task_timeout = orch_section.get('task_timeout', DEFAULT_TASK_TIMEOUT)
        self.aggregation_strategy = orch_section.get('aggregation_strategy', 'consensus')
        self.silent = silent
        
        # Enhanced agent factory with configuration support
        self.agent_factory = agent_factory or self._create_agent_with_config
        self.config_path = config_path
        
        # Track agent progress
        self.agent_progress = {}
        self.agent_results = {}
        self.progress_lock = threading.Lock()
    
    def _create_agent_with_config(self, agent_id=None, silent=True):
        """Create agent with agent-specific configuration"""
        return create_agent(
            config_path=self.config_path,
            agent_id=agent_id,
            silent=silent,
            preloaded_config=self.config
        )
    
    def _create_orchestrator_agent(self, silent=True):
        """Create agent specifically for orchestrator operations (question generation, synthesis)"""
        # If a custom agent factory is provided, use it
        if self.agent_factory != self._create_agent_with_config:
            return self.agent_factory(silent=silent)
            
        # Otherwise, use the standard orchestrator agent creation
        # Create a temporary agent configuration for orchestrator
        orchestrator_agent_config = self.orchestrator_config.copy()
        
        # Use orchestrator-specific model if configured
        if 'model' in self.orchestrator_config:
            orchestrator_agent_config['model'] = self.orchestrator_config['model']
        
        if 'provider' in self.orchestrator_config:
            provider = self.orchestrator_config['provider']
            if provider == "claude_code":
                from claude_code_cli_provider import ClaudeCodeCLIAgent
                return ClaudeCodeCLIAgent(
                    config_path=self.config_path,
                    silent=silent,
                    agent_config=orchestrator_agent_config
                )
            else:
                from agent import OpenRouterAgent
                return OpenRouterAgent(
                    config_path=self.config_path,
                    silent=silent,
                    agent_config=orchestrator_agent_config
                )
        else:
            # Use default agent creation
            return create_agent(config_path=self.config_path, silent=silent, preloaded_config=self.config)
    
    def decompose_task(self, user_input: str, num_agents: int) -> List[str]:
        """Use AI to dynamically generate different questions based on user input.
        
        Creates specialized sub-questions that approach the topic from different
        angles (research, analysis, verification, alternatives, etc.).
        
        Parameters
        ----------
        user_input : str
            The original user query
        num_agents : int
            Number of questions to generate
            
        Returns
        -------
        List[str]
            List of generated questions, one per agent
            
        Notes
        -----
        Falls back to simple question variations if AI generation fails.
        """
        if not self.silent:
            print(f"🧠 Generating {num_agents} specialized questions...")
        
        decompose_start = time.time()
        
        # Create orchestrator-specific agent for question generation
        question_agent = self._create_orchestrator_agent(silent=True)
        
        # Get question generation prompt from config
        prompt_template = self.config['orchestrator']['question_generation_prompt']
        generation_prompt = prompt_template.format(
            user_input=user_input,
            num_agents=num_agents
        )
        
        # Remove task completion tool to avoid issues
        question_agent.tools = [tool for tool in question_agent.tools if tool.get('function', {}).get('name') != 'mark_task_complete']
        question_agent.tool_mapping = {name: func for name, func in question_agent.tool_mapping.items() if name != 'mark_task_complete'}
        
        try:
            # Get AI-generated questions
            response = question_agent.run(generation_prompt)
            
            # Parse JSON response
            questions = json.loads(response.strip())
            
            # Validate we got the right number of questions
            if len(questions) != num_agents:
                raise ValueError(f"Expected {num_agents} questions, got {len(questions)}")
            
            if not self.silent:
                print(f"✅ Generated questions in {time.time() - decompose_start:.1f}s")
                for i, q in enumerate(questions, 1):
                    print(f"   Agent {i}: {q[:60]}..." if len(q) > 60 else f"   Agent {i}: {q}")
            
            return questions
            
        except (json.JSONDecodeError, ValueError) as e:
            # Fallback: create simple variations if AI fails
            return [
                f"Research comprehensive information about: {user_input}",
                f"Analyze and provide insights about: {user_input}",
                f"Find alternative perspectives on: {user_input}",
                f"Verify and cross-check facts about: {user_input}"
            ][:num_agents]
    
    def update_agent_progress(self, agent_id: int, status: str, result: str = None):
        """Thread-safe progress tracking"""
        with self.progress_lock:
            self.agent_progress[agent_id] = status
            if result is not None:
                self.agent_results[agent_id] = result
    
    def run_agent_parallel(self, agent_id: int, subtask: str) -> Dict[str, Any]:
        """Run a single agent with the given subtask.
        
        This method is designed to be called in parallel by ThreadPoolExecutor.
        It tracks progress and handles errors gracefully.
        
        Parameters
        ----------
        agent_id : int
            Unique identifier for this agent (0-based)
        subtask : str
            The specific question/task for this agent
            
        Returns
        -------
        dict
            Result dictionary containing:
            - agent_id: The agent identifier
            - status: "success" or "error"
            - response: The agent's response or error message
            - execution_time: Time taken in seconds
        """
        try:
            self.update_agent_progress(agent_id, "INITIALIZING...")
            
            # Show which agent is starting if timing debug is enabled
            if os.environ.get('TIMING_DEBUG', 'false').lower() == 'true':
                print(f"\n🚀 Starting Agent {agent_id + 1} with task: {subtask[:50]}...")
            
            # Create agent with specific ID for configuration lookup
            agent_start = time.time()
            agent_config_id = f"agent_{agent_id + 1}"  # agent_1, agent_2, etc.
            agent = self.agent_factory(agent_id=agent_config_id, silent=True)
            
            if os.environ.get('TIMING_DEBUG', 'false').lower() == 'true':
                print(f"⏱️  Agent {agent_id + 1} initialized in {time.time() - agent_start:.2f}s")
            
            self.update_agent_progress(agent_id, "PROCESSING...")
            
            start_time = time.time()
            response = agent.run(subtask)
            execution_time = time.time() - start_time
            
            self.update_agent_progress(agent_id, "COMPLETED", response)
            
            if os.environ.get('TIMING_DEBUG', 'false').lower() == 'true':
                print(f"✅ Agent {agent_id + 1} completed in {execution_time:.1f}s")
            
            return {
                "agent_id": agent_id,
                "status": "success", 
                "response": response,
                "execution_time": execution_time
            }
            
        except Exception as e:
            # Simple error handling
            self.update_agent_progress(agent_id, f"FAILED: {str(e)[:30]}...")
            if os.environ.get('TIMING_DEBUG', 'false').lower() == 'true':
                print(f"❌ Agent {agent_id + 1} failed: {str(e)}")
            
            return {
                "agent_id": agent_id,
                "status": "error",
                "response": f"Error: {str(e)}",
                "execution_time": 0
            }
    
    def aggregate_results(self, agent_results: List[Dict[str, Any]]) -> str:
        """Combine results from all agents into a comprehensive final answer.
        
        Uses AI synthesis to intelligently combine multiple perspectives into
        a coherent response. Falls back to concatenation if synthesis fails.
        
        Parameters
        ----------
        agent_results : List[dict]
            Results from all agents, including failed ones
            
        Returns
        -------
        str
            Synthesized final answer combining all successful responses
        """
        successful_results = [r for r in agent_results if r["status"] == "success"]
        
        if not successful_results:
            return "All agents failed to provide results. Please try again."
        
        # Extract responses for aggregation
        responses = [r["response"] for r in successful_results]
        
        if self.aggregation_strategy == "consensus":
            return self._aggregate_consensus(responses, successful_results)
        else:
            # Default to consensus
            return self._aggregate_consensus(responses, successful_results)
    
    def _aggregate_consensus(self, responses: List[str], _results: List[Dict[str, Any]]) -> str:
        """
        Use one final AI call to synthesize all agent responses into a coherent answer.
        """
        if len(responses) == 1:
            return responses[0]
        
        # Create orchestrator-specific agent for synthesis
        synthesis_agent = self._create_orchestrator_agent(silent=True)
        
        # Build agent responses section
        agent_responses_text = ""
        for i, response in enumerate(responses, 1):
            agent_responses_text += f"=== AGENT {i} RESPONSE ===\n{response}\n\n"
        
        # Get synthesis prompt from config and format it
        synthesis_prompt_template = self.config['orchestrator']['synthesis_prompt']
        synthesis_prompt = synthesis_prompt_template.format(
            num_responses=len(responses),
            agent_responses=agent_responses_text
        )
        
        # Completely remove all tools from synthesis agent to force direct response
        synthesis_agent.tools = []
        synthesis_agent.tool_mapping = {}
        
        # Get the synthesized response
        try:
            final_answer = synthesis_agent.run(synthesis_prompt)
            return final_answer
        except Exception as e:
            # Log the error for debugging
            print(f"\n🚨 SYNTHESIS FAILED: {str(e)}")
            print("📋 Falling back to concatenated responses\n")
            # Fallback: if synthesis fails, concatenate responses
            combined = []
            for i, response in enumerate(responses, 1):
                combined.append(f"=== Agent {i} Response ===")
                combined.append(response)
                combined.append("")
            return "\n".join(combined)
    
    def get_progress_status(self) -> Dict[int, str]:
        """Get current progress status for all agents"""
        with self.progress_lock:
            return self.agent_progress.copy()
    
    def orchestrate(self, user_input: str) -> str:
        """Main orchestration method for multi-agent analysis.
        
        Coordinates the entire process: decomposition, parallel execution,
        and synthesis.
        
        Parameters
        ----------
        user_input : str
            The user's query or request
            
        Returns
        -------
        str
            Comprehensive answer synthesized from all agents
            
        Examples
        --------
        >>> orchestrator = TaskOrchestrator(silent=True)
        >>> result = orchestrator.orchestrate("Explain quantum computing")
        >>> print(result)
        "Quantum computing is... [comprehensive multi-perspective answer]"
        """
        orchestrate_start = time.time()
        
        # Reset progress tracking
        self.agent_progress = {}
        self.agent_results = {}
        
        if not self.silent:
            print(f"\n🎯 Orchestrating with {self.num_agents} parallel agents...")
        
        # Decompose task into subtasks
        subtasks = self.decompose_task(user_input, self.num_agents)
        
        # Initialize progress tracking
        for i in range(self.num_agents):
            self.agent_progress[i] = "QUEUED"
        
        # Execute agents in parallel
        agent_results = []
        
        with ThreadPoolExecutor(max_workers=self.num_agents) as executor:
            # Submit all agent tasks
            future_to_agent = {
                executor.submit(self.run_agent_parallel, i, subtasks[i]): i 
                for i in range(self.num_agents)
            }
            
            # Collect results as they complete
            try:
                for future in as_completed(future_to_agent, timeout=self.task_timeout):
                    try:
                        result = future.result()
                        agent_results.append(result)
                    except Exception as e:
                        agent_id = future_to_agent[future]
                        agent_results.append({
                            "agent_id": agent_id,
                            "status": "timeout",
                            "response": f"Agent {agent_id + 1} timed out or failed: {str(e)}",
                            "execution_time": self.task_timeout
                        })
            except TimeoutError:
                # Handle agents that didn't complete in time
                for future, agent_id in future_to_agent.items():
                    if not future.done():
                        agent_results.append({
                            "agent_id": agent_id,
                            "status": "timeout",
                            "response": f"Agent {agent_id + 1} timed out",
                            "execution_time": self.task_timeout
                        })
                        future.cancel()
        
        # Sort results by agent_id for consistent output
        agent_results.sort(key=lambda x: x["agent_id"])
        
        # Aggregate results
        if not self.silent:
            print(f"\n🔀 Synthesizing {len(agent_results)} agent responses...")
        
        synthesis_start = time.time()
        final_result = self.aggregate_results(agent_results)
        
        total_time = time.time() - orchestrate_start
        if not self.silent:
            print(f"✅ Synthesis completed in {time.time() - synthesis_start:.1f}s")
            print(f"⏱️  Total orchestration time: {total_time:.1f}s")
        
        return final_result