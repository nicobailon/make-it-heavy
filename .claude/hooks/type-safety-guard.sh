#!/bin/bash
# Python Type Safety Guard Hook - Detects and blocks Python type safety violations
# Enforces Python type safety guidelines from python-type-safety.md

# Read JSON input from stdin
input=$(cat)

# Extract tool name
tool_name=$(echo "$input" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)

# Only check Edit, Write, MultiEdit
case "$tool_name" in
  Edit|Write|MultiEdit) ;;
  *) exit 0 ;;
esac

# Extract file path
file_path=$(echo "$input" | grep -o '"path"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)

# Only Python files
if [[ "$file_path" != *.py ]]; then
  exit 0
fi

# Extract content
content=""
case "$tool_name" in
  "Write")
    content=$(echo "$input" | grep -o '"content"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
    ;;
  *)
    content=$(echo "$input" | grep -o '"new_string"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
    ;;
esac

# Pattern: Any, object, # type: ignore
if echo "$content" | grep -qE '\b[Aa]ny\b|:\s*[Aa]ny\b|->\s*[Aa]ny\b|\[\s*[Aa]ny\s*\]|\bobject\b|:\s*object\b|->\s*object\b|#\s*type:\s*ignore'; then
    # Emit guidance and block
    cat >&2 << 'EOF'
## Python Type Safety Violation Detected

This change introduces code that violates the strict type-safety requirements defined in python-type-safety.md.

Forbidden patterns detected:
- Usage of `Any` or `object` which widens types
- `# type: ignore` suppression comments

### How to resolve
1. Replace `Any`/`object` with precise, narrow types (Literal, TypedDict, NewType, dataclass, Enum, etc.).
2. Remove `# type: ignore` and address the underlying issue.
3. Run `mypy --strict` and ensure zero errors.
4. Verify PyLance shows no type issues.
5. Confirm tests and runtime type-validation pass.

See the "Critical Type Safety Rules" and "Type Problem Resolution Protocol" sections in python-type-safety.md for detailed guidance.

Operation aborted to protect type precision.
EOF
    exit 2
fi

exit 0