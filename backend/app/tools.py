"""
Built-in tools the model can call via Groq's OpenAI-compatible function
calling. Both are self-contained (no external API, no cost) so they work
the same in local dev as anywhere else.
"""
import ast
import operator
import math
from datetime import datetime, timezone

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": (
                "Evaluate a basic arithmetic expression (+, -, *, /, **, %, "
                "parentheses). Use this for any math instead of doing it "
                "in your head."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "e.g. '12 * (3 + 4)'",
                    }
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time in UTC. Use when the user asks what time or date it is.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _safe_eval(node):
    """Evaluates a parsed arithmetic AST node, allowing only numbers and
    the operators in _ALLOWED_OPS -- deliberately not a general `eval`."""
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_OPS:
        left, right = _safe_eval(node.left), _safe_eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e100):
            raise ValueError("Exponent too large")
        result = _ALLOWED_OPS[type(node.op)](left, right)
        if isinstance(result, complex) or not math.isfinite(result) or abs(result) > 1e100:
            raise ValueError("Result too large")
        return result
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_OPS:
        return _ALLOWED_OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("Unsupported expression")


def calculate(expression: str) -> str:
    try:
        if not isinstance(expression, str) or len(expression) > 1000:
            raise ValueError("Expression too long")
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)
        return str(result)
    except Exception:
        return "Error: could not evaluate that expression."


def get_current_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def call_tool(name: str, arguments: dict) -> str:
    if not isinstance(arguments, dict):
        return "Error: tool arguments must be an object."
    if name == "calculate":
        return calculate(arguments.get("expression", ""))
    if name == "get_current_time":
        return get_current_time()
    return f"Error: unknown tool '{name}'"
