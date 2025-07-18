#!/bin/bash
# Python Type Safety Guard Hook - Detects and blocks Python type safety violations
# Enforces Python type safety guidelines from python-type-safety.md

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Warning: jq is not installed. Type safety guard hook is disabled." >&2
    echo "Install jq with: brew install jq (macOS) or apt-get install jq (Linux)" >&2
    exit 0
fi

# Read JSON input from stdin
input=$(cat)

# Validate JSON
if ! echo "$input" | jq . >/dev/null 2>&1; then
    echo "Error: Invalid JSON input to type safety guard hook" >&2
    exit 0
fi

# Extract tool name using jq
tool_name=$(echo "$input" | jq -r '.tool_name // empty' 2>/dev/null)

# Only check Edit, Write, MultiEdit
case "$tool_name" in
  Edit|Write|MultiEdit) ;;
  *) exit 0 ;;
esac

# Extract file path using jq
file_path=$(echo "$input" | jq -r '.path // empty' 2>/dev/null)

# Only Python files
if [[ "$file_path" != *.py ]]; then
  exit 0
fi

# Extract content based on tool type
content=""
case "$tool_name" in
  "Write")
    content=$(echo "$input" | jq -r '.content // empty' 2>/dev/null)
    ;;
  "Edit")
    content=$(echo "$input" | jq -r '.new_string // empty' 2>/dev/null)
    ;;
  "MultiEdit")
    # For MultiEdit, concatenate all new_string values
    content=$(echo "$input" | jq -r '.edits[]?.new_string // empty' 2>/dev/null | tr '\n' ' ')
    ;;
esac

# If content extraction failed, exit gracefully
if [ -z "$content" ]; then
    exit 0
fi

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