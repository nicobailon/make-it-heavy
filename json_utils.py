"""JSON utilities for safe parsing and validation."""

import json
import logging
from typing import Any, Optional, TypeVar, Union, Callable

logger = logging.getLogger(__name__)

T = TypeVar('T')


class JSONParseError(Exception):
    """Custom exception for JSON parsing errors with context."""
    
    def __init__(self, message: str, raw_data: Optional[str] = None, original_error: Optional[Exception] = None):
        super().__init__(message)
        self.raw_data = raw_data
        self.original_error = original_error


def safe_json_parse(
    data: str,
    default: Optional[T] = None,
    validator: Optional[Callable[[Any], bool]] = None,
    error_context: str = "JSON parsing"
) -> Union[T, Any]:
    """
    Safely parse JSON data with proper error handling and optional validation.
    
    Parameters
    ----------
    data : str
        The JSON string to parse
    default : Optional[T]
        Default value to return if parsing fails (None by default)
    validator : Optional[Callable[[Any], bool]]
        Optional validation function that should return True if data is valid
    error_context : str
        Context string for error messages
    
    Returns
    -------
    Union[T, Any]
        Parsed JSON data or default value if parsing fails
        
    Raises
    ------
    JSONParseError
        If default is None and parsing fails, or if validation fails
    """
    try:
        # Strip whitespace and check for empty data
        data = data.strip()
        if not data:
            if default is not None:
                logger.warning(f"{error_context}: Empty JSON data, using default")
                return default
            raise JSONParseError(f"{error_context}: Empty JSON data")
        
        # Parse JSON
        parsed = json.loads(data)
        
        # Run validation if provided
        if validator and not validator(parsed):
            raise JSONParseError(
                f"{error_context}: Validation failed",
                raw_data=data[:500] if len(data) > 500 else data
            )
        
        return parsed
        
    except json.JSONDecodeError as e:
        error_msg = f"{error_context}: Invalid JSON at line {e.lineno}, column {e.colno} - {e.msg}"
        logger.error(error_msg)
        logger.debug(f"Raw data: {data[:200]}..." if len(data) > 200 else f"Raw data: {data}")
        
        if default is not None:
            logger.info("Using default value due to JSON parse error")
            return default
            
        raise JSONParseError(error_msg, raw_data=data[:500], original_error=e)
        
    except Exception as e:
        error_msg = f"{error_context}: Unexpected error - {str(e)}"
        logger.error(error_msg)
        
        if default is not None:
            logger.info("Using default value due to unexpected error")
            return default
            
        raise JSONParseError(error_msg, raw_data=data[:500], original_error=e)


def validate_question_list(data: Any) -> bool:
    """
    Validate that data is a list of strings suitable for agent questions.
    
    Parameters
    ----------
    data : Any
        Data to validate
        
    Returns
    -------
    bool
        True if data is a valid list of question strings
    """
    if not isinstance(data, list):
        logger.error(f"Expected list, got {type(data).__name__}")
        return False
    
    if not data:
        logger.error("Question list is empty")
        return False
    
    for i, item in enumerate(data):
        if not isinstance(item, str):
            logger.error(f"Question {i} is not a string: {type(item).__name__}")
            return False
        if not item.strip():
            logger.error(f"Question {i} is empty or whitespace")
            return False
    
    return True


def parse_json_with_fallback(
    data: str,
    expected_type: type,
    fallback_parser: Optional[Callable[[str], Any]] = None,
    error_context: str = "JSON parsing"
) -> Any:
    """
    Parse JSON with a fallback parser for malformed but recoverable data.
    
    Parameters
    ----------
    data : str
        The JSON string to parse
    expected_type : type
        Expected type of the parsed result
    fallback_parser : Optional[Callable[[str], Any]]
        Function to attempt parsing if JSON fails
    error_context : str
        Context string for error messages
        
    Returns
    -------
    Any
        Parsed data
        
    Raises
    ------
    JSONParseError
        If both JSON parsing and fallback parsing fail
    """
    try:
        result = safe_json_parse(data, error_context=error_context)
        if not isinstance(result, expected_type):
            raise JSONParseError(
                f"{error_context}: Expected {expected_type.__name__}, got {type(result).__name__}"
            )
        return result
        
    except JSONParseError as e:
        if fallback_parser:
            logger.warning(f"{error_context}: Attempting fallback parser due to: {e}")
            try:
                result = fallback_parser(data)
                if isinstance(result, expected_type):
                    return result
                else:
                    logger.error(f"Fallback parser returned wrong type: {type(result).__name__}")
            except Exception as fallback_error:
                logger.error(f"Fallback parser failed: {fallback_error}")
        
        raise e


def extract_json_from_text(text: str) -> Optional[str]:
    """
    Attempt to extract JSON from text that might contain extra content.
    
    Useful for AI responses that might include explanatory text around JSON.
    
    Parameters
    ----------
    text : str
        Text that might contain JSON
        
    Returns
    -------
    Optional[str]
        Extracted JSON string or None if not found
    """
    # Try to find JSON array
    import re
    
    # Look for array pattern
    array_match = re.search(r'\[\s*"[^"]*"(?:\s*,\s*"[^"]*")*\s*\]', text, re.DOTALL)
    if array_match:
        return array_match.group(0)
    
    # Look for object pattern
    object_match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
    if object_match:
        return object_match.group(0)
    
    return None