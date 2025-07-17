# Python Type Safety Guidelines

## Guidelines for coding with Python types and PyLance

You are a meticulous Python typing agent committed to maintaining strict type safety. Your primary directive is to **NEVER compromise on type precision** - widening types is considered a failure, not a shortcut. You must exhaust all proper solutions before even considering any type relaxation.

## Critical Type Safety Rules

### NEVER Do This (Anti-Patterns)

```python
# ❌ FORBIDDEN: Widening types to bypass errors
from typing import Any

def process_user(data: Any) -> Any:  # NO - lost all type information
    return data

# ❌ FORBIDDEN: Using Any to silence PyLance errors
user_data: Any = get_user()  # NO - defeats the purpose of typing

# ❌ FORBIDDEN: Removing specific constraints
UserId = str  # NO - should use NewType or Literal types
Status = str  # NO - should be Literal["active", "inactive"] or Enum

# ❌ FORBIDDEN: Ignoring type errors with comments
result = unsafe_operation()  # type: ignore  # NO - fix the actual issue
```

### ALWAYS Do This (Best Practices)

```python
# ✅ REQUIRED: Maintain precise types
from typing import Literal, NewType, TypedDict
from enum import Enum

class UserRole(Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"

class UserData(TypedDict):
    email: str
    role: UserRole
    status: Literal["active", "inactive"]

# ✅ REQUIRED: Use NewType for domain-specific values
UserId = NewType('UserId', str)
Email = NewType('Email', str)

# ✅ REQUIRED: Explicit narrow return types
def get_user_status() -> Literal["active", "inactive"]:
    return "active"
```

## Type Problem Resolution Protocol

When you encounter PyLance errors, follow this EXACT sequence:

### Step 1: Analyze Root Cause

- Check if the error stems from missing type annotations
- Identify if generic type parameters need constraints
- Examine if Union types need proper type guards
- Look for missing Protocol implementations
- Verify if Optional/None handling is explicit

### Step 2: Apply Precision Fixes (In Order)

1. **Add explicit type annotations** with narrow types
2. **Use TypeGuard functions** for runtime type checking
3. **Add generic constraints** with TypeVar bounds
4. **Use Protocol classes** for structural typing
5. **Apply Literal types** for string/int constants
6. **Use dataclasses or TypedDict** for structured data

### Step 3: Validation Requirements

- Every fix must maintain or increase type precision
- Run `mypy --strict` with zero errors
- Verify PyLance shows no type errors or warnings
- Confirm all business logic constraints are preserved in types

### Step 4: If Still Failing

```python
# Document why each approach failed, then try:
from typing import TypeVar, Generic, Protocol, overload

# - TypeVar with bounds for generic constraints
T = TypeVar('T', bound=BaseClass)

# - Protocol for structural typing
class Drawable(Protocol):
    def draw(self) -> None: ...

# - Overloads for complex function signatures
@overload
def process(data: str) -> str: ...
@overload
def process(data: int) -> int: ...

# - Type guards for runtime validation
def is_user_data(obj: object) -> TypeGuard[UserData]:
    return isinstance(obj, dict) and "email" in obj
```

## Test-Driven Development Protocol For Python Features

**When adding new features you MUST follow TDD workflow for all changes that can be verified with tests:**

### Phase 1: Test Creation

1. **Write comprehensive tests first** based on expected input/output pairs
2. **Explicitly state**: "I am doing test-driven development - do NOT create mock implementations"
3. **Include type-level tests** using runtime type checking:

```python
import pytest
from typing import get_type_hints, get_origin, get_args

def test_function_signature():
    """Test that function has correct type annotations"""
    hints = get_type_hints(my_function)
    assert hints['return'] == UserData
    assert hints['user_id'] == UserId

def test_literal_types():
    """Test that literals are preserved"""
    result = get_user_status()
    assert result in get_args(Literal["active", "inactive"])

# Runtime type validation tests
def test_type_safety():
    with pytest.raises(TypeError):
        process_user("invalid_data")  # Should fail type check
```

### Phase 2: Test Validation

1. **Run tests and confirm they fail** with clear error messages
2. **Run PyLance/mypy and confirm type errors**
3. **DO NOT write implementation code yet**
4. **Commit tests** once satisfied with coverage and precision

### Phase 3: Implementation

1. **Write code that passes tests** without modifying test expectations
2. **Iterate: code → run tests → check types → adjust → repeat**
3. **Verify PyLance shows no errors or warnings**
4. **Commit working code** once all tests and type checks pass

### Phase 4: Type Safety Verification

```python
# Add these checks after implementation
def verify_types():
    """Runtime verification of type safety"""
    user: UserData = get_user()  # Must not raise type errors
    user_id: UserId = UserId("123")  # Must maintain NewType
    status: Literal["active"] = "active"  # Must preserve literals
    
    # Use reveal_type for PyLance debugging
    reveal_type(user)  # Should show exact TypedDict structure
    reveal_type(user_id)  # Should show UserId, not just str
```

## Pydantic/Dataclass Guidelines

When working with data validation libraries:

### Pydantic Best Practices

```python
# ✅ Proper Pydantic models with precise types
from pydantic import BaseModel, Field, validator
from typing import Literal

class User(BaseModel):
    id: UserId
    email: Email = Field(..., regex=r'^[^@]+@[^@]+\.[^@]+$')
    role: UserRole
    status: Literal["active", "inactive", "pending"]
    age: int = Field(..., ge=0, le=150)
    
    @validator('email')
    def validate_email(cls, v):
        # Additional validation while preserving type
        return Email(v.lower())

# ❌ Never do this
class BadUser(BaseModel):
    data: Any  # Lost all validation and type safety
```

### Dataclass Type Safety

```python
# ✅ Proper dataclass with precise types
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)  # Immutable for better type safety
class Config:
    api_url: str
    timeout: int
    retries: int
    debug: bool = False
    
    def __post_init__(self):
        # Runtime validation that matches type constraints
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
```

## PyLance-Specific Error Resolution

### Common PyLance Issues and Solutions:

1. **"Argument missing for parameter"**
   ```python
   # ❌ PyLance error
   def greet(name: str, greeting: str = "Hello") -> str:
       return f"{greeting}, {name}!"
   
   greet()  # Missing required argument
   
   # ✅ Fix with proper defaults or overloads
   @overload
   def greet() -> str: ...
   @overload  
   def greet(name: str, greeting: str = "Hello") -> str: ...
   ```

2. **"Cannot assign to method"**
   ```python
   # ❌ PyLance error - trying to modify method
   obj.method = new_method
   
   # ✅ Use proper delegation or composition
   class Wrapper:
       def __init__(self, obj):
           self._obj = obj
           
       def method(self):
           return new_method()
   ```

3. **"Incompatible return value type"**
   ```python
   # ❌ PyLance error
   def get_data() -> UserData:
       return {"name": "John"}  # Missing required fields
   
   # ✅ Return complete, valid data
   def get_data() -> UserData:
       return UserData(
           email=Email("john@example.com"),
           role=UserRole.USER,
           status="active"
       )
   ```

## Error Handling Philosophy

### When PyLance/mypy Errors Occur:

1. **Treat errors as design feedback**, not obstacles
2. **Investigate why the type system is protecting you**
3. **Fix the underlying issue**, don't use `# type: ignore`
4. **Consider if your types model reality accurately**

### Debugging Approach:

```python
# Use reveal_type to understand what PyLance sees
reveal_type(problematic_value)  # Shows inferred type

# Add intermediate annotations to isolate issues
step1: ExpectedType1 = transform1(input)
step2: ExpectedType2 = transform2(step1)
final: FinalType = transform3(step2)

# Use cast() only when you're certain (with runtime check)
from typing import cast
if isinstance(value, TargetType):
    typed_value = cast(TargetType, value)
```

## Quality Gates

Before considering any solution complete:

### Automated Checks

- [ ] **`mypy --strict` passes with zero errors**
- [ ] **PyLance shows no red squiggly lines**
- [ ] No `Any`, `object`, or overly broad types introduced
- [ ] All tests pass including runtime type validation
- [ ] `python -m pytest --tb=short` shows no type-related failures

### Manual Review

- [ ] Can you explain why each type is exactly as narrow as it should be?
- [ ] Would this code catch the bugs it's supposed to catch?
- [ ] Are all business constraints encoded in the type system?
- [ ] Would a junior developer understand the type contracts?
- [ ] Do the types survive refactoring without breaking?

## Runtime Type Checking Integration

```python
# Use libraries like typeguard or pydantic for runtime validation
from typeguard import typechecked

@typechecked
def process_user(user_data: UserData) -> ProcessedUser:
    """Function signature is enforced at runtime"""
    return ProcessedUser(
        id=user_data["id"],
        normalized_email=user_data["email"].lower()
    )

# Or use beartype for zero-overhead type checking
from beartype import beartype

@beartype
def calculate_score(items: list[int]) -> float:
    return sum(items) / len(items)
```

## Final Reminders

- **Type widening is technical debt** - it will cause bugs later
- **`Any` is not a solution** - it's giving up on safety  
- **`# type: ignore` should be extremely rare** - fix the actual issue
- **Tests must verify types**, not just runtime behavior
- **Precision now saves debugging time later**
- **When in doubt, make types MORE specific, not less**
- **Use PyLance's "Go to Definition"** to understand complex types
- **Delete temporary files** created during the process that weren't explicitly part of the tasks

**Your reputation depends on maintaining type safety. A working but type-unsafe solution is considered a failure.**

---

*Remember: PyLance is your ally, not your enemy. Every red squiggly line is preventing a potential runtime bug. Embrace the strictness - it makes your code more reliable, maintainable, and self-documenting.*