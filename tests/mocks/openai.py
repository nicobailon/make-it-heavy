from unittest.mock import MagicMock
import json


class MockOpenAIClient:
    """Mock OpenAI client that returns deterministic responses for testing."""

    def __init__(self, responses=None):
        self.responses = responses or []
        self.call_count = 0
        self.chat = MagicMock()
        self.chat.completions = MagicMock()
        self.chat.completions.create = self._create_completion

    def _create_completion(self, **kwargs):
        """Returns mock completions based on the message content."""
        messages = kwargs.get("messages", [])
        tools = kwargs.get("tools", [])

        # Extract the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                user_message = msg.get("content", "")
                break

        # Determine response based on content
        if self.responses and self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response

        # Default responses based on patterns
        if (
            "calculate" in user_message.lower()
            or "math" in user_message.lower()
            or "*" in user_message
            or "×" in user_message
        ):
            return self._create_calculation_response(user_message, tools)
        elif "search" in user_message.lower():
            return self._create_search_response(user_message, tools)
        elif "file" in user_message.lower():
            return self._create_file_response(user_message, tools)
        elif "complete" in user_message.lower() or "done" in user_message.lower():
            return self._create_completion_response(tools)
        else:
            return self._create_default_response()

    def _create_calculation_response(self, message, tools):
        """Creates a response that uses the calculate tool."""
        # Extract numbers from the message
        if "15" in message and ("*" in message or "×" in message) and "7" in message:
            expression = "15 * 7"
            expected_result = 105
        elif "2" in message and "2" in message:
            expression = "2 + 2"
            expected_result = 4
        elif "144" in message and "square root" in message.lower():
            expression = "sqrt(144)"
            expected_result = 12
        else:
            expression = "1 + 1"
            expected_result = 2

        if tools and any(
            t.get("function", {}).get("name") == "calculate" for t in tools
        ):
            return self._create_tool_response("calculate", {"expression": expression})
        else:
            return self._create_text_response(f"The result is {expected_result}")

    def _create_search_response(self, message, tools):
        """Creates a response that uses the search tool."""
        if tools and any(
            t.get("function", {}).get("name") == "search_web" for t in tools
        ):
            return self._create_tool_response("search_web", {"query": "test search"})
        else:
            return self._create_text_response("I found some search results for you.")

    def _create_file_response(self, message, tools):
        """Creates a response for file operations."""
        if "read" in message.lower():
            if tools and any(
                t.get("function", {}).get("name") == "read_file" for t in tools
            ):
                return self._create_tool_response("read_file", {"path": "test.txt"})
            else:
                return self._create_text_response("File content: test data")
        else:
            if tools and any(
                t.get("function", {}).get("name") == "write_file" for t in tools
            ):
                return self._create_tool_response(
                    "write_file", {"path": "output.txt", "content": "test"}
                )
            else:
                return self._create_text_response("File written successfully.")

    def _create_completion_response(self, tools):
        """Creates a task completion response."""
        if tools and any(
            t.get("function", {}).get("name") == "mark_task_complete" for t in tools
        ):
            return self._create_tool_response(
                "mark_task_complete",
                {
                    "task_summary": "Test task completed",
                    "completion_message": "All tests passed",
                },
            )
        else:
            return self._create_text_response("Task completed successfully.")

    def _create_default_response(self):
        """Creates a default text response."""
        return self._create_text_response("This is a test response.")

    def _create_text_response(self, content):
        """Creates a mock text response."""
        message = MagicMock()
        message.content = content
        message.tool_calls = []

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "stop"

        response = MagicMock()
        response.choices = [choice]

        return response

    def _create_tool_response(self, tool_name, arguments):
        """Creates a mock tool call response."""
        tool_call = MagicMock()
        tool_call.id = f"call_{tool_name}_123"
        tool_call.type = "function"
        tool_call.function = MagicMock()
        tool_call.function.name = tool_name
        tool_call.function.arguments = json.dumps(arguments)

        message = MagicMock()
        message.content = None
        message.tool_calls = [tool_call]

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = "tool_calls"

        response = MagicMock()
        response.choices = [choice]

        return response

    def add_response(self, response):
        """Add a specific response to the queue."""
        self.responses.append(response)

    def reset(self):
        """Reset the client state."""
        self.call_count = 0
        self.responses = []
