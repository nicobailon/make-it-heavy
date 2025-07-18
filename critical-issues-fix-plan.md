# Fix Plan for Critical Security and Performance Issues

## Overview
I'll fix 6 critical issues identified in the code review, prioritized by severity: security vulnerabilities first, then race conditions, and finally performance optimizations.

## 🔴 Critical Security Fix

### 1. Shell Injection Risk in type-safety-guard.sh
**Issue**: Using grep/cut on untrusted JSON input allows command injection
**Fix**: Replace shell parsing with jq for safe JSON handling
- Install jq dependency check
- Replace all grep/cut JSON parsing with jq commands
- Add input validation and escaping
- Test with malicious payloads

## 🔴 Critical Concurrency Fixes

### 2. Race Condition in Cache Invalidation (config_utils.py)
**Issue**: Cache generation increment not atomic with cache clear
**Fix**: Use existing _cache_lock for synchronization
- Wrap invalidate_config_cache operations in _cache_lock
- Ensure atomic increment and clear operations
- Add thread safety test

### 3. Silent Exception Handling (agent.py)
**Issue**: Bare except clause hides critical errors
**Fix**: Specific exception handling with logging
- Replace bare except with queue.Full exception
- Add warning-level logging for pool overflow
- Include agent cleanup status in logs

## 🟡 Performance Optimizations

### 4. Inefficient Pool Search (agent.py)
**Issue**: O(n) linear search through queue on every request
**Fix**: Hybrid dictionary + queue approach
- Add dict mapping config_key -> list of agents
- Keep queue for LRU eviction order
- O(1) lookup for cache hits

### 5. Expensive Configuration Hashing (agent.py)
**Issue**: Full JSON serialization + MD5 on every agent creation
**Fix**: Lightweight configuration key generation
- Cache config keys per agent_id
- Use hash of only changing fields
- Add config_key caching mechanism

## 🟠 Bug Fix

### 6. Memory Leak in Timeout Handling (orchestrator.py)
**Issue**: Timeout errors lose original exception context
**Fix**: Preserve full error information
- Store original TimeoutError/Exception objects
- Add debug_info field with full traceback
- Include in agent results for debugging

## Implementation Order
1. Security fix (shell injection) - Highest priority
2. Race condition fix - Data integrity
3. Exception handling - Debugging visibility
4. Performance optimizations - Lower priority
5. Memory leak fix - Quality of life

## Testing Strategy
- Create temporary test files (test_security_fixes.py, etc.)
- Run tests to verify each fix
- Delete test files after verification
- Use existing test suite to ensure no regressions