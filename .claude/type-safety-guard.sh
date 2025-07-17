#!/bin/bash
# Python Type Safety Guard Hook - Detects and blocks Python type safety violations
# Enforces Python type safety guidelines from python-type-safety.md

# Read JSON input from stdin
input=$(cat)

# Extract tool name and content using jq (if available) or grep
tool_name=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)

# Only check Edit, Write, MultiEdit operations on Python files
if [[ "$tool_name" != "Edit" && "$tool_name" != "Write" && "$tool_name" != "MultiEdit" ]]; then
    exit 0
fi

# Check if this is a Python file operation
file_path=$(echo "$input" | grep -o '"path"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
if [[ "$file_path" != *.py ]]; then
    exit 0
fi

# Extract content based on tool type
content=""
case "$tool_name" in
    "Write")
        content=$(echo "$input" | grep -o '"content"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
        ;;
    "Edit")
        content=$(echo "$input" | grep -o '"new_string"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
        ;;
    "MultiEdit")
        content=$(echo "$input" | grep -o '"new_string"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
        ;;
esac

# Check for 'any' type usage (simple pattern matching)
if echo "$content" | grep -qE '\b[Aa]ny\b|:\s*any\b|->\s*any\b|\[\s*any\s*\]'; then
    cat >&2 << 'EOF'
## TypeScript Guidelines

### Guidelines for TypeScript

You are committed to maintaining strict type safety. Your primary directive is to **NEVER compromise on type precision** - widening types is considered a failure, not a shortcut. You must exhaust all proper solutions before even considering any type relaxation.

### Critical Type Safety Rules

#### NEVER Do This (Anti-Patterns)

```typescript
// ❌ FORBIDDEN: Widening types to bypass errors
const schema = z.object({
  email: z.any(),           // NO - lost email validation
  role: z.string(),         // NO - lost enum constraints
  status: z.any()           // NO - lost literal types
})

// ❌ FORBIDDEN: Using 'any' to silence errors
function processData(input: any): any { ... }

// ❌ FORBIDDEN: Removing specific constraints
type UserId = string        // NO - should be branded/validated
```

#### ALWAYS Do This (Best Practices)

```typescript
// ✅ REQUIRED: Maintain precise types
const schema = z.object({
  email: z.string().email(),
  role: z.enum(["admin", "user", "moderator"]),
  status: z.literal("active"),
});

// ✅ REQUIRED: Use as const for configuration
const config = {
  apiUrl: "https://api.com",
  timeout: 5000,
  retries: 3,
} as const;

// ✅ REQUIRED: Explicit narrow types
type UserId = string & { readonly __brand: "UserId" };
```

### Type Problem Resolution Protocol

When you encounter type errors, follow this EXACT sequence:

#### Step 1: Analyze Root Cause

- Identify if the error stems from type widening
- Check if `const` vs `let` declarations are causing issues
- Examine if object properties need `as const` assertions
- Look for missing generic constraints

#### Step 2: Apply Precision Fixes (In Order)

1. **Add `as const` assertions** to prevent widening
2. **Use explicit type annotations** with narrow types
3. **Add generic constraints** to maintain type information
4. **Use branded types** for domain-specific values
5. **Apply readonly modifiers** where appropriate

#### Step 3: Validation Requirements

- Every fix must maintain or increase type precision
- Run TypeScript compiler with `--strict` mode
- Verify no `any` types were introduced
- Confirm all business logic constraints are preserved

#### Step 4: If Still Failing

```typescript
// Document why each approach failed, then try:
// - Union types with proper discrimination
// - Conditional types for complex scenarios
// - Mapped types for transformations
// - Template literal types for string patterns
```
EOF
    exit 2  # Exit with error code to block operation
fi

exit 0