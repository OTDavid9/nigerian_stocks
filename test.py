from openai import OpenAI
import json
import ast
import operator
from typing import Any, Callable


class StockAgent:
    """
    OOP wrapper around Ollama's OpenAI-compatible Responses API.

    Responsibilities:
    - Maintain system prompt
    - Maintain conversation history
    - Send requests to Ollama
    - Execute tools
    - Feed tool results back to the model
    - Return the final response
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gemma4:31b-cloud",
        base_url: str = "https://ollama.com/v1",
        system_prompt: str | None = None,
    ):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key,
        )

        self.model = model

        self.system_prompt = system_prompt or """
You are a helpful AI assistant.

You have access to tools that you can use when necessary.

Rules:
1. Use tools when they are required to answer the user's request.
2. Never invent the result of a tool call.
3. If a tool fails, clearly explain the failure.
4. Use previous conversation context when answering.
5. Be concise but useful.
6. Do not expose internal tool execution details unless necessary.
"""

        # Conversation history
        self.history: list[dict[str, Any]] = []

        # Tool definitions
        self.tools = [
            {
                "type": "function",
                "name": "get_horoscope",
                "description": "Get today's horoscope for an astrological sign.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sign": {
                            "type": "string",
                            "description": "An astrological sign like Taurus or Aquarius",
                        }
                    },
                    "required": ["sign"],
                },
            },
            {
                "type": "function",
                "name": "get_weather",
                "description": "Get the current weather for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "The city to get weather information for",
                        }
                    },
                    "required": ["city"],
                },
            },
            {
                "type": "function",
                "name": "calculate",
                "description": "Perform a mathematical calculation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "A mathematical expression",
                        }
                    },
                    "required": ["expression"],
                },
            },
        ]

        # Map tool names to Python functions
        self.available_tools: dict[str, Callable] = {
            "get_horoscope": self.get_horoscope,
            "get_weather": self.get_weather,
            "calculate": self.calculate,
        }

    # =========================================================
    # TOOLS
    # =========================================================

    def get_horoscope(self, sign: str):
        return {
            "sign": sign,
            "horoscope": (
                f"{sign}: Next Tuesday you will befriend a baby otter."
            ),
        }

    def get_weather(self, city: str):
        # Replace this with a real API later
        return {
            "city": city,
            "temperature": "27°C",
            "condition": "Partly cloudy",
        }

    def calculate(self, expression: str):

        # Safe-ish calculator for basic arithmetic.
        # Avoid eval() in production.

        allowed_operators = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
        }

        def evaluate(node):

            if isinstance(node, ast.Expression):
                return evaluate(node.body)

            if isinstance(node, ast.Constant):
                if isinstance(node.value, (int, float)):
                    return node.value
                raise ValueError("Invalid constant")

            if isinstance(node, ast.BinOp):
                left = evaluate(node.left)
                right = evaluate(node.right)

                operator_function = allowed_operators.get(type(node.op))

                if operator_function is None:
                    raise ValueError("Operator not allowed")

                return operator_function(left, right)

            if isinstance(node, ast.UnaryOp):
                operand = evaluate(node.operand)

                if isinstance(node.op, ast.USub):
                    return -operand

                if isinstance(node.op, ast.UAdd):
                    return operand

                raise ValueError("Unary operator not allowed")

            raise ValueError("Invalid expression")

        try:
            tree = ast.parse(expression, mode="eval")

            result = evaluate(tree)

            return {
                "expression": expression,
                "result": result,
            }

        except Exception as e:
            return {
                "expression": expression,
                "error": str(e),
            }

    # =========================================================
    # SYSTEM PROMPT
    # =========================================================

    def _build_input(self):
        """
        Always put the system prompt first.

        Then append conversation history.
        """

        return [
            {
                "role": "system",
                "content": self.system_prompt,
            },
            *self.history,
        ]

    # =========================================================
    # TOOL EXECUTION
    # =========================================================

    def _execute_tool(self, tool_call):

        tool_name = tool_call.name

        try:
            arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError:
            return {
                "error": "Invalid tool arguments"
            }

        print(f"\nTool: {tool_name}")
        print(f"Arguments: {arguments}")

        if tool_name not in self.available_tools:

            return {
                "error": f"Unknown tool: {tool_name}"
            }

        function = self.available_tools[tool_name]

        try:
            result = function(**arguments)

            print(f"Result: {result}")

            return result

        except Exception as e:

            return {
                "error": str(e)
            }

    # =========================================================
    # CHAT
    # =========================================================

    def chat(self, user_message: str) -> str:

        # -----------------------------------------------------
        # 1. Add user message to history
        # -----------------------------------------------------

        self.history.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        # -----------------------------------------------------
        # 2. Ask model
        # -----------------------------------------------------

        response = self.client.responses.create(
            model=self.model,
            tools=self.tools,
            input=self._build_input(),
        )

        # -----------------------------------------------------
        # 3. Save model output
        # -----------------------------------------------------

        self.history.extend(response.output)

        # -----------------------------------------------------
        # 4. Execute tools
        # -----------------------------------------------------

        tool_calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if tool_calls:

            for tool_call in tool_calls:

                result = self._execute_tool(tool_call)

                self.history.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(result),
                    }
                )

            # -------------------------------------------------
            # 5. Ask model again with tool results
            # -------------------------------------------------

            final_response = self.client.responses.create(
                model=self.model,
                tools=self.tools,
                input=self._build_input(),
            )

            # Save final model output
            self.history.extend(final_response.output)

            return final_response.output_text

        # -----------------------------------------------------
        # 6. No tools were required
        # -----------------------------------------------------

        return response.output_text

    # =========================================================
    # HISTORY MANAGEMENT
    # =========================================================

    def get_history(self):
        return self.history

    def clear_history(self):
        self.history = []

    def get_system_prompt(self):
        return self.system_prompt

    def set_system_prompt(self, system_prompt: str):
        self.system_prompt = system_prompt