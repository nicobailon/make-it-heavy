# Migration Guide: Agent and Orchestrator Customization

This guide helps you migrate to the new agent and orchestrator customization features in Make It Heavy.

## What's New

### 1. Per-Agent Configuration
Each agent can now have its own:
- AI model
- Provider (OpenRouter or Claude Code)
- System prompt
- Configuration parameters

### 2. Orchestrator Model Separation
The orchestrator can use different models for:
- Question generation
- Response synthesis

### 3. Configuration Inheritance
Agent configurations inherit from global settings, allowing fine-grained overrides.

## Backward Compatibility

**All existing configurations continue to work unchanged.** The new features are opt-in.

## Migration Examples

### Example 1: Basic Usage (No Changes Needed)

If you're happy with all agents using the same model, no changes are required:

```yaml
provider: "openrouter"
openrouter:
  api_key: "YOUR_KEY"
  model: "openai/gpt-4"
```

### Example 2: Different Models for Different Agents

To use specialized models for each agent:

```yaml
provider: "openrouter"  # Default provider

openrouter:
  api_key: "YOUR_KEY"
  model: "openai/gpt-4"  # Default model

# Add this new section
agents:
  agent_1:
    model: "anthropic/claude-3.5-sonnet"  # Deep analysis
  agent_2:
    model: "openai/gpt-4.1-mini"  # Fast responses
  agent_3:
    model: "google/gemini-2.0-flash-001"  # Latest features
  agent_4:
    model: "meta-llama/llama-3.1-70b"  # Open source
```

### Example 3: Mixed Providers

To use different providers for different agents:

```yaml
provider: "claude_code"  # Default to Claude

# Configure both providers
claude_code:
  model: "claude-sonnet-4-20250514"

openrouter:
  api_key: "YOUR_KEY"
  model: "openai/gpt-4"

# Mix providers across agents
agents:
  agent_1:
    provider: "openrouter"
    model: "anthropic/claude-3.5-sonnet"
  agent_2:
    # Uses default Claude Code provider
    model: "claude-opus-4-20250514"
```

### Example 4: Custom System Prompts

To specialize agent behaviors:

```yaml
agents:
  agent_1:
    system_prompt: |
      You are a research specialist. Focus on finding comprehensive, 
      factual information from reliable sources.
  
  agent_2:
    system_prompt: |
      You are a critical analyst. Look for potential issues, 
      contradictions, and alternative viewpoints.
  
  agent_3:
    system_prompt: |
      You are a creative problem solver. Suggest innovative 
      solutions and think outside the box.
```

### Example 5: Orchestrator Customization

To use a different model for orchestrator operations:

```yaml
orchestrator:
  # Existing settings remain
  parallel_agents: 4
  task_timeout: 300
  
  # Add model customization
  provider: "openrouter"
  model: "anthropic/claude-3.5-sonnet"  # Better synthesis
```

## Configuration Reference

### Agent Configuration Options

```yaml
agents:
  agent_N:  # where N is 1, 2, 3, 4
    provider: "openrouter" | "claude_code"  # Optional
    model: "model-name"                     # Optional
    system_prompt: "custom prompt"          # Optional
    api_key: "agent-specific-key"          # Optional (OpenRouter)
    max_iterations: 10                      # Optional
```

### Orchestrator Configuration Options

```yaml
orchestrator:
  # Standard settings
  parallel_agents: 4
  task_timeout: 300
  aggregation_strategy: "consensus"
  
  # Model customization (all optional)
  provider: "openrouter" | "claude_code"
  model: "model-name"
  
  # Prompts remain the same
  question_generation_prompt: "..."
  synthesis_prompt: "..."
```

## Best Practices

1. **Start Simple**: Begin with just model changes, then add custom prompts
2. **Test Incrementally**: Change one agent at a time and test
3. **Monitor Costs**: Different models have different pricing
4. **Consider Context Windows**: Ensure models have sufficient context (200k+ for orchestrator)
5. **Mix Strategically**: Use expensive models for complex tasks, cheaper for simple ones

## Troubleshooting

### Issue: Agent using wrong model
**Solution**: Check that agent_N matches the number (agent_1, agent_2, etc.)

### Issue: Configuration not taking effect
**Solution**: Clear configuration cache in tests with `clear_config_cache()`

### Issue: Provider errors
**Solution**: Ensure all required fields are present for each provider:
- OpenRouter: api_key, model
- Claude Code: model

### Issue: Validation errors
**Solution**: Run validation before deployment:
```python
from config_utils import load_config, validate_config
config = load_config("config.yaml")
validate_config(config)
```

## Performance Notes

- Configuration is cached for performance
- Thread-safe for parallel agent execution
- No performance impact for default configurations

## Programmatic Usage

### Creating Agents with Specific IDs

The enhanced `create_agent` function now supports agent-specific configurations:

```python
from agent import create_agent

# Create agent with specific ID (will use agent_1 config if defined)
agent = create_agent(agent_id="agent_1")

# Pre-load configuration for performance
from config_utils import load_config
config = load_config("config.yaml")
agent = create_agent(agent_id="agent_2", preloaded_config=config)

# Legacy usage still works
agent = create_agent()  # Uses global config
```

### Legacy Compatibility

For existing code, these wrappers maintain backward compatibility:

```python
from agent import create_agent_legacy, create_agent_original

# Both work exactly as before
agent = create_agent_legacy()
agent = create_agent_original()
```

- Minimal overhead for customized configurations

## Need Help?

- Check examples in `config.yaml`
- Run tests: `python run_tests.py`
- Review test files for usage examples