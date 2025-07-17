# Performance Optimization Guide for Make It Heavy with Claude Code

## Issue Analysis

The slow performance when using Claude Code provider is due to:

1. **Parallel Claude CLI Initialization** - Each of the 4 agents spawns a separate Claude CLI process
2. **Large System Prompts** - Each agent gets a ~3000+ character system prompt with all tool instructions
3. **Multiple Iterations** - Each agent can run up to 10 iterations (turns) before completing
4. **Subprocess Overhead** - Starting Claude CLI subprocess adds latency for each agent

## Debugging

To enable detailed timing information:

```bash
export TIMING_DEBUG=true
uv run make_it_heavy.py
```

This will show:
- Time for each initialization step
- Progress of each agent
- Time spent in each phase
- Which agent is processing what task

## Optimization Recommendations

### 1. Reduce Parallel Agents (Immediate)
Edit `config.yaml`:
```yaml
orchestrator:
  parallel_agents: 2  # Reduce from 4 to 2
```

### 2. Limit Max Iterations (Immediate)
```yaml
agent:
  max_iterations: 5  # Reduce from 10 to 5
```

### 3. Use Faster Model (Immediate)
```yaml
claude_code:
  model: "claude-3-haiku-20240307"  # Faster than Sonnet 4
```

### 4. Implement Agent Pooling (Future)
Instead of creating new agents each time:
- Pre-initialize a pool of Claude CLI agents
- Reuse them across requests
- This would eliminate repeated initialization overhead

### 5. Cache System Prompts (Future)
- System prompts are identical for all agents
- Could be cached to disk after first generation
- Reduces prompt building time from ~0.1s to near zero

### 6. Sequential Processing Option (Alternative)
For resource-constrained environments, add a sequential mode:
```yaml
orchestrator:
  parallel_agents: 1  # Sequential processing
  # OR add new option:
  execution_mode: "sequential"  # vs "parallel"
```

### 7. Optimize Tool Discovery (Future)
- Tool discovery happens for each agent
- Could be done once and shared
- Would save ~0.1s per agent

## Performance Expectations

With Claude Code provider:
- Each agent initialization: ~1-2s
- Each Claude turn: ~5-15s depending on complexity
- Total time for 4 agents with 3-5 turns each: 60-300s

With optimizations (2 agents, 5 max turns, Haiku model):
- Expected reduction: 50-70% faster
- Total time: 30-90s

## Monitoring Performance

The added instrumentation shows:
- 🧠 Question generation phase
- 🚀 Agent initialization
- 🔄 Claude Code turns with elapsed time
- ✅ Agent completion times
- 🔀 Synthesis phase
- ⏱️ Total orchestration time

## Alternative: Use OpenRouter

For faster performance, switch back to OpenRouter:
```yaml
provider: "openrouter"
```

OpenRouter benefits:
- No subprocess overhead
- Direct API calls
- Better suited for parallel execution
- 5-10x faster for simple queries