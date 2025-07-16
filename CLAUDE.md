# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

"Make It Heavy" is a Python framework that emulates Grok Heavy functionality using a multi-agent system built on OpenRouter's API. It features intelligent agent orchestration for comprehensive, multi-perspective analysis.

## Development Commands

### Running the Application

```bash
# Single agent mode - runs one agent with all tools
uv run main.py

# Multi-agent orchestration mode (Grok Heavy emulation) - runs 4 parallel agents
uv run make_it_heavy.py
```

### Installing Dependencies

```bash
# Using uv (recommended)
uv pip install -r requirements.txt

# Using standard pip
pip install -r requirements.txt
```

## Architecture Overview

### Core Components

1. **Agent System (`agent.py`)**
   - Implements the agentic loop that continues until task completion
   - Manages tool discovery and execution through `tools/` directory
   - Handles OpenRouter API communication with function calling

2. **Orchestrator (`orchestrator.py`)**
   - Dynamically generates specialized questions using AI
   - Manages parallel execution of multiple agents
   - Synthesizes responses from all agents into comprehensive output

3. **Tool System (`tools/`)**
   - Auto-discovery mechanism in `__init__.py` loads all tools automatically
   - Base class `BaseTool` defines the interface for all tools
   - New tools can be added by creating files that inherit from `BaseTool`

### Key Design Patterns

- **Dynamic Tool Loading**: Tools are discovered at runtime from the `tools/` directory
- **Agentic Loop**: Agents iterate until they call `mark_task_complete`
- **Parallel Execution**: Orchestrator uses ThreadPoolExecutor for concurrent agent runs
- **AI-Driven Decomposition**: Question generation and response synthesis use the configured LLM

## Configuration

All configuration is in `config.yaml`:
- Provider selection (`openrouter` or `claude_code`)
- OpenRouter API settings (key, model selection)
- Claude Code settings (model, max turns, permission mode)
- Agent behavior (max iterations, system prompts)
- Orchestrator settings (parallel agents count, timeouts)
- Tool-specific settings

### Using Claude Code Provider

To use Claude Code instead of OpenRouter:
1. Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`
2. Change provider in config.yaml: `provider: "claude_code"`
3. Configure Claude Code settings in the `claude_code` section
4. The default model is Claude 4 (claude-sonnet-4-20250514)

#### How Claude Code Integration Works

The Claude Code provider uses a tool bridge approach:
- `use_tool.py` acts as a bridge between Claude Code and our custom tools
- Claude Code runs `python use_tool.py <tool_name> '<args>...</args>'` via its Bash tool
- Uses XML format to avoid JSON escaping issues (e.g., `<args><expression>2+2</expression></args>`)
- This allows Claude Code to use all our custom tools (search_web, calculate, etc.)
- The agent continues iterating until `mark_task_complete` is called

#### Technical Implementation
- Uses subprocess to call Claude Code CLI directly
- Parses streaming JSON output for real-time progress
- Handles tool permissions with `--allowedTools "Bash(python use_tool.py *)"`
- Detects task completion from tool calls

## Important Considerations

- **Context Window**: When selecting models in config.yaml, ensure high context window (200k+ tokens) for orchestrator synthesis
- **API Key**: Must be set in config.yaml before running
- **Tool Development**: New tools must implement `name`, `description`, `parameters`, and `execute` methods from `BaseTool`


# Test Generation Guidelines

## Core Principle
You are a behavior-focused test engineer. Your job is to verify REQUIREMENTS, not encode existing code behavior. Always ask: "What should this code accomplish?" not "What does this code currently do?"

## Decision Framework: What Tests to Write

### 1. ALWAYS Test These (High Value)
- **Public API contracts**: Input/output behavior that users depend on
- **Business logic outcomes**: Account balance changes, order totals, user permissions
- **Error conditions**: Invalid inputs, edge cases, failure scenarios  
- **State transitions**: User login/logout, workflow steps, data transformations
- **Integration boundaries**: API responses, database operations, external service calls

### 2. SOMETIMES Test These (Context Dependent)
- **Performance characteristics**: Only if explicitly required (response times, memory usage)
- **Complex algorithms**: When business logic is intricate and bug-prone
- **Security boundaries**: Authentication, authorization, data validation
- **Configuration changes**: Environment-specific behavior

### 3. NEVER Test These (Low/Negative Value)
- **Implementation details**: Private methods, internal state, specific function calls
- **Framework behavior**: React lifecycle, Express middleware (unless customized)
- **Third-party libraries**: Axios, Lodash, moment.js (assume they work)
- **Trivial getters/setters**: Simple property access without logic
- **Code coverage targets**: Don't write tests just to hit percentage goals

## Test Quality Checklist

Before writing any test, verify it passes ALL criteria:

✅ **Behavioral Focus**: Tests observable outcomes, not internal mechanics
✅ **Requirements Based**: Verifies a specific business requirement or user story  
✅ **Survival Test**: Will pass after refactoring implementation for performance
✅ **Failure Value**: Will catch real bugs when broken
✅ **User Perspective**: Tests through public APIs as users would interact
✅ **Clear Intent**: Test name explains WHAT should happen, not HOW

## Anti-Patterns to Avoid

❌ Testing that internal functions are called (use spies/mocks minimally)
❌ Asserting exact object structures (test behavior, not shape)
❌ Testing multiple concerns in one test (keep focused)
❌ Hardcoding specific values that could change (use meaningful assertions)
❌ Testing framework defaults (React renders, Express handles routes)
❌ Writing tests for the sake of coverage metrics

## Prompt Requirements for Humans

When humans request tests, require this information:
- **What should this code accomplish?** (business requirements)
- **What are the success/failure scenarios?** (expected behaviors)
- **Who uses this and how?** (user perspective)
- **What would break the business if this failed?** (critical paths)

If humans only provide code without context, respond:
"I need behavioral requirements to write valuable tests. What should this code accomplish from a user's perspective? What are the expected outcomes for different inputs?"

## Test Type Decisions

### Unit Tests (70% of test suite)
- Pure business logic functions
- Data transformations and calculations  
- Input validation and error handling
- Algorithm correctness

### Integration Tests (20% of test suite)  
- Component interactions within your system
- Database operations with real schema
- API endpoint behavior with realistic data
- Service communication patterns

### E2E Tests (10% of test suite)
- Critical user journeys only
- Happy path through entire system
- Core business workflows
- High-value user scenarios

## Example Good vs Bad Tests

### GOOD: Behavior-focused
```javascript
test('should reject transfer when insufficient funds', () => {
  const account = new Account(100);
  expect(() => account.transfer(150))
    .toThrow('Insufficient funds');
  expect(account.balance).toBe(100);
});
```

### BAD: Implementation-focused  
```javascript
test('should call validateFunds method', () => {
  const spy = jest.spyOn(account, 'validateFunds');
  account.transfer(50);
  expect(spy).toHaveBeenCalledWith(50);
});
```

## Success Metrics

Measure test quality by:
- **Bug detection rate**: Do tests catch real issues?
- **Refactoring safety**: Do tests survive code improvements?
- **Development speed**: Do tests help or hinder feature development?
- **Confidence level**: Do tests provide genuine assurance?

NOT by:
- Code coverage percentages
- Number of tests written
- Test execution speed alone
- Framework compliance

Remember: One well-designed behavioral test is worth more than ten implementation tests that break on every refactor.


## Test Failure Response Protocol

CRITICAL: When tests fail, the failure is valuable feedback about missing or incorrect implementation. Never modify tests to accommodate broken code. No fabricating passed results for tests that you are having trouble with

WHEN A TEST FAILS:
1. First assume the test is correct and revealing a real issue
2. Analyze what business requirement or behavior the test expects
3. Implement the missing functionality in the production code
4. Only modify the test if it's testing implementation details rather than business requirements

FORBIDDEN RESPONSES TO TEST FAILURES:
- Changing assertions to match current broken behavior
- Relaxing validation in tests when implementation is incomplete
- Adding conditional logic to handle "edge cases" that are actually bugs
- Commenting out or skipping failing tests without investigation
- Modifying expected values to match incorrect actual values

CORRECT TDD RESPONSE PATTERN:
Red → Green → Refactor
- Red: Test fails because feature is missing/broken
- Green: Implement the feature to make test pass
- Refactor: Improve code while keeping tests passing

DECISION FRAMEWORK:
Before modifying any test, ask:
1. Does this test verify a business requirement or expected behavior?
2. Is the current implementation actually correct?
3. Would changing this test hide a real bug from future developers?
4. Am I accommodating broken code instead of fixing it?

If the test expects input validation, error handling, or specific business logic, implement that functionality rather than removing the expectation.

VALIDATION EXAMPLE:
Test expects: Constructor throws with invalid input
Current code: Constructor accepts anything
CORRECT: Add validation to constructor
INCORRECT: Remove validation expectation from test

The goal is working software that meets requirements, not just passing tests.

## Test Stability Requirements

CRITICAL: Write stable, deterministic tests that focus on behavior contracts, not implementation details.

FORBIDDEN:
- Asserting internal state, private methods, or implementation mechanics
- Hard-coded timing, random values, or external dependencies without control
- Tests that depend on execution order or shared state
- Testing "how" instead of "what" the system delivers

REQUIRED:
- Deterministic: Same input → same output, every time
- Isolated: Each test owns its setup/cleanup, runs independently
- Behavior-focused: Test user-visible outcomes and business requirements
- Implementation-agnostic: Survives refactoring of internal code

STABILITY TEST:
If your test breaks when you:
- Rename private methods → Too brittle
- Change internal structures → Too brittle  
- Run in different order → Not isolated
- Run multiple times → Flaky
- Run on different machines → Environment-dependent

Fix test design, don't accommodate instability.

PATTERN: Mock externals, control randomness, test through public interfaces, assert outcomes not steps.
