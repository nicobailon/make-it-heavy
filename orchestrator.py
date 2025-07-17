import json
import time
import threading
import os
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
from typing import List, Dict, Any, Optional
from agent import create_agent
from config_utils import get_orchestrator_config, load_config, validate_config
from constants import DEFAULT_TASK_TIMEOUT

# Set up logging
logger = logging.getLogger(__name__)

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
        self.config_path = config_path or "config.yaml"
        
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
                    agent_config=orchestrator_agent_config,
                    config=self.config
                )
        else:
            # Use default agent creation
            return create_agent(config_path=self.config_path, silent=silent, preloaded_config=self.config)
    
    def _generate_questions_with_retry(self, prompt: str, question_agent, max_attempts: int = 3) -> str:
        """Generate questions with retry logic and exponential backoff
        
        Parameters
        ----------
        prompt : str
            The prompt for question generation
        question_agent : Agent
            The agent to use for generation
        max_attempts : int
            Maximum number of retry attempts
            
        Returns
        -------
        str
            The agent's response
            
        Raises
        ------
        Exception
            If all attempts fail
        """
        last_error = None
        wait_time = 1  # Start with 1 second
        
        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    logger.info(f"Question generation retry attempt {attempt + 1}/{max_attempts}")
                    time.sleep(wait_time)
                    wait_time *= 2  # Exponential backoff
                
                return question_agent.run(prompt)
                
            except Exception as e:
                last_error = e
                logger.warning(f"Question generation attempt {attempt + 1} failed: {str(e)}")
        
        raise last_error
    
    def _generate_contextual_fallback_questions(self, user_input: str, num_agents: int, error: Optional[Exception] = None) -> List[str]:
        """Generate context-aware fallback questions based on error type and user input
        
        Parameters
        ----------
        user_input : str
            The original user query
        num_agents : int
            Number of questions needed
        error : Exception, optional
            The error that occurred during generation
            
        Returns
        -------
        List[str]
            Fallback questions tailored to the context
        """
        # Log the fallback scenario
        if error:
            logger.warning(f"Using contextual fallback questions due to error: {type(error).__name__}")
        else:
            logger.info("Using contextual fallback questions")
        
        # Analyze user input to determine query type
        input_lower = user_input.lower()
        
        # Technical/programming queries
        if any(word in input_lower for word in ['code', 'program', 'function', 'debug', 'error', 'implement']):
            base_questions = [
                f"Analyze the technical requirements and implementation details for: {user_input}",
                f"Research best practices and common patterns related to: {user_input}",
                f"Identify potential issues and debugging strategies for: {user_input}",
                f"Explore alternative solutions and approaches to: {user_input}"
            ]
        # Research/informational queries
        elif any(word in input_lower for word in ['what', 'how', 'why', 'when', 'who', 'explain']):
            base_questions = [
                f"Provide comprehensive background information about: {user_input}",
                f"Explain the key concepts and principles behind: {user_input}",
                f"Analyze the implications and applications of: {user_input}",
                f"Compare different perspectives and viewpoints on: {user_input}"
            ]
        # Problem-solving queries
        elif any(word in input_lower for word in ['solve', 'fix', 'resolve', 'troubleshoot', 'issue']):
            base_questions = [
                f"Diagnose the root causes and contributing factors for: {user_input}",
                f"Propose step-by-step solutions to address: {user_input}",
                f"Evaluate risks and potential complications when solving: {user_input}",
                f"Research proven methods and case studies for: {user_input}"
            ]
        # Analysis/evaluation queries
        elif any(word in input_lower for word in ['analyze', 'evaluate', 'compare', 'review', 'assess']):
            base_questions = [
                f"Conduct detailed analysis of key aspects regarding: {user_input}",
                f"Evaluate strengths, weaknesses, and trade-offs for: {user_input}",
                f"Compare with alternatives and benchmarks related to: {user_input}",
                f"Provide data-driven insights and metrics about: {user_input}"
            ]
        # Default fallback for general queries
        else:
            base_questions = [
                f"Research comprehensive information about: {user_input}",
                f"Analyze and provide insights about: {user_input}",
                f"Find alternative perspectives on: {user_input}",
                f"Verify and cross-check facts about: {user_input}"
            ]
        
        # Extend questions if we need more than 4
        if num_agents > len(base_questions):
            additional_questions = [
                f"Explore future trends and developments related to: {user_input}",
                f"Identify key stakeholders and their perspectives on: {user_input}",
                f"Examine historical context and evolution of: {user_input}",
                f"Assess practical applications and real-world examples of: {user_input}"
            ]
            base_questions.extend(additional_questions)
        
        return base_questions[:num_agents]
    
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
            # Get AI-generated questions with retry logic
            response = self._generate_questions_with_retry(generation_prompt, question_agent)
            
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
            
        except Exception as e:
            # Log the error for debugging
            logger.warning(f"Question generation failed after retries: {str(e)}")
            
            # Use contextual fallback questions
            return self._generate_contextual_fallback_questions(user_input, num_agents, error=e)
    
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
    
    def aggregate_results(self, agent_results: List[Dict[str, Any]], original_query: str = None) -> str:
        """Combine results from all agents into a comprehensive final answer.
        
        Uses AI synthesis to intelligently combine multiple perspectives into
        a coherent response. Falls back to concatenation if synthesis fails.
        
        Parameters
        ----------
        agent_results : List[dict]
            Results from all agents, including failed ones
        original_query : str, optional
            The original user query for context
            
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
            return self._aggregate_consensus(responses, successful_results, original_query)
        else:
            # Default to consensus
            return self._aggregate_consensus(responses, successful_results, original_query)
    
    def _check_synthesis_tools_available(self) -> bool:
        """Check if synthesis agent has required tools
        
        Returns
        -------
        bool
            True if tools are available, False otherwise
        """
        try:
            synthesis_agent = self._create_orchestrator_agent(silent=True)
            return hasattr(synthesis_agent, 'tools') and len(synthesis_agent.tools) > 0
        except Exception:
            return False
    
    def _simple_synthesis(self, responses: List[str], original_query: str) -> str:
        """Simple synthesis without tools - concatenate and summarize
        
        Parameters
        ----------
        responses : List[str]
            Agent responses to combine
        original_query : str
            The original user query
            
        Returns
        -------
        str
            Simple combined response
        """
        if len(responses) == 1:
            return responses[0]
        
        # Build a structured summary
        summary_parts = [
            f"Combined analysis for '{original_query}':",
            "",
            "=" * 60,
            ""
        ]
        
        for i, response in enumerate(responses, 1):
            summary_parts.extend([
                f"**Agent {i} Response:**",
                response,
                "",
                "-" * 40,
                ""
            ])
        
        # Add a simple conclusion
        summary_parts.extend([
            "=" * 60,
            "",
            f"The above responses provide different perspectives on: {original_query}",
            "Each agent has analyzed the query from its unique angle to provide comprehensive coverage."
        ])
        
        return "\n".join(summary_parts)
    
    def _aggregate_consensus(self, responses: List[str], _results: List[Dict[str, Any]], original_query: str = None) -> str:
        """
        Use one final AI call to synthesize all agent responses into a coherent answer.
        With graceful degradation if tools are unavailable.
        """
        if len(responses) == 1:
            return responses[0]
        
        # Use provided query or default
        if not original_query:
            original_query = "the given query"  # Default fallback
        
        # Check if synthesis tools are available
        if not self._check_synthesis_tools_available():
            logger.info("Synthesis tools unavailable, using simple synthesis")
            return self._simple_synthesis(responses, original_query)
        
        try:
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
            final_answer = synthesis_agent.run(synthesis_prompt)
            return final_answer
            
        except Exception as e:
            # Log the error for debugging
            logger.warning(f"Advanced synthesis failed, using simple synthesis: {str(e)}")
            if not self.silent:
                print(f"\n🚨 SYNTHESIS FAILED: {str(e)}")
                print("📋 Falling back to simple synthesis\n")
            
            # Use the improved simple synthesis
            return self._simple_synthesis(responses, original_query)
    
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
        final_result = self.aggregate_results(agent_results, user_input)
        
        total_time = time.time() - orchestrate_start
        if not self.silent:
            print(f"✅ Synthesis completed in {time.time() - synthesis_start:.1f}s")
            print(f"⏱️  Total orchestration time: {total_time:.1f}s")
        
        return final_result