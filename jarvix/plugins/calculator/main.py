"""Calculator plugin — safe mathematical expression evaluation.

Provides a 'calculate' tool that evaluates basic math expressions
without using eval(). Uses a safe tokenizer and parser.
"""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Dict, Optional

from jarvix.core.logger import get_logger
from jarvix.core.tool_registry import Tool, ToolResult, tool
from jarvix.core.permissions import PermissionLevel

_LOG = get_logger("jarvix.plugins.calculator")

# Supported operators
_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Supported functions (only if allow_functions setting is True)
_FUNCTIONS = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    # Math module functions
    "sqrt": math.sqrt,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "floor": math.floor,
    "ceil": math.ceil,
    "pi": math.pi,
    "e": math.e,
}

# Plugin settings
_settings: Dict[str, Any] = {
    "precision": 10,
    "allow_functions": False,
}


def get_settings() -> Dict[str, Any]:
    """Return current plugin settings."""
    return dict(_settings)


def set_settings(settings: Dict[str, Any]) -> None:
    """Update plugin settings."""
    _settings.update(settings)
    _LOG.info("Calculator settings updated: %s", _settings)


class SafeEvaluator(ast.NodeVisitor):
    """Safe AST evaluator for mathematical expressions."""

    def __init__(self, allow_functions: bool = False):
        self._allow_functions = allow_functions

    def visit(self, node: ast.AST) -> Any:
        """Visit a node and return its evaluated value."""
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        elif isinstance(node, ast.Constant):  # Python 3.8+
            return node.value
        elif isinstance(node, ast.Num):  # Python < 3.8
            return node.n
        elif isinstance(node, ast.BinOp):
            return self._eval_binop(node)
        elif isinstance(node, ast.UnaryOp):
            return self._eval_unaryop(node)
        elif isinstance(node, ast.Call):
            return self._eval_call(node)
        elif isinstance(node, ast.Name):
            return self._eval_name(node)
        else:
            raise ValueError(f"Unsupported AST node: {type(node).__name__}")

    def _eval_binop(self, node: ast.BinOp) -> Any:
        left = self.visit(node.left)
        right = self.visit(node.right)
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        return _OPERATORS[op_type](left, right)

    def _eval_unaryop(self, node: ast.UnaryOp) -> Any:
        operand = self.visit(node.operand)
        op_type = type(node.op)
        if op_type not in _OPERATORS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _OPERATORS[op_type](operand)

    def _eval_call(self, node: ast.Call) -> Any:
        if not self._allow_functions:
            raise ValueError("Function calls not allowed")

        if not isinstance(node.func, ast.Name):
            raise ValueError("Only direct function calls allowed")

        func_name = node.func.id
        if func_name not in _FUNCTIONS:
            raise ValueError(f"Unknown function: {func_name}")

        func = _FUNCTIONS[func_name]
        args = [self.visit(arg) for arg in node.args]
        kwargs = {kw.arg: self.visit(kw.value) for kw in node.keywords}
        return func(*args, **kwargs)

    def _eval_name(self, node: ast.Name) -> Any:
        if not self._allow_functions:
            raise ValueError("Variables not allowed")

        if node.id not in _FUNCTIONS:
            raise ValueError(f"Unknown name: {node.id}")
        return _FUNCTIONS[node.id]


def evaluate_expression(expr: str, allow_functions: bool = False) -> float:
    """Safely evaluate a mathematical expression.

    Args:
        expr: The expression string to evaluate
        allow_functions: Whether to allow function calls

    Returns:
        The evaluated result as a float

    Raises:
        ValueError: If the expression is invalid or uses unsupported features
    """
    # Basic sanitization - only allow safe characters
    allowed_chars = set("0123456789+-*/.%() ")
    if allow_functions:
        allowed_chars.update("abcdefghijklmnopqrstuvwxyz_")
    else:
        allowed_chars.update("abcdefghijklmnopqrstuvwxyz_")  # Allow for constants like pi, e

    for ch in expr:
        if ch not in allowed_chars:
            raise ValueError(f"Invalid character: {ch}")

    # Parse and evaluate
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid syntax: {e}")

    evaluator = SafeEvaluator(allow_functions=allow_functions)
    result = evaluator.visit(tree)

    # Round to precision
    precision = _settings.get("precision", 10)
    if isinstance(result, float):
        return round(result, precision)
    return result


@tool("calculate", permission=PermissionLevel.SAFE, description="Evaluate a mathematical expression safely")
class CalculateTool(Tool):
    name = "calculate"
    description = "Evaluate a mathematical expression (e.g., '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)')"
    permission = PermissionLevel.SAFE

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate (e.g., '2 + 3 * 4', 'sqrt(16)')",
                },
                "precision": {
                    "type": "integer",
                    "description": "Decimal precision for result (overrides plugin setting)",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["expression"],
        }

    async def execute(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        expr = args.get("expression", "").strip()
        precision = args.get("precision")

        if not expr:
            return ToolResult.failure("expression is required")

        ctx.check_cancelled()

        # Use override precision if provided
        original_precision = None
        if precision is not None:
            original_precision = _settings.get("precision", 10)
            _settings["precision"] = precision

        try:
            result = evaluate_expression(expr, allow_functions=_settings.get("allow_functions", False))
            return ToolResult.success(
                f"{expr} = {result}",
                data={"expression": expr, "result": result}
            )
        except ValueError as e:
            return ToolResult.failure(f"Invalid expression: {e}")
        except ZeroDivisionError:
            return ToolResult.failure("Division by zero")
        except Exception as e:
            _LOG.exception("Calculation failed for: %s", expr)
            return ToolResult.failure(f"Calculation failed: {e}")
        finally:
            if original_precision is not None:
                _settings["precision"] = original_precision


def register(tool_registry: Any) -> None:
    """Register the calculator tool with the tool registry."""
    tool_registry.register("calculate", CalculateTool())
    _LOG.info("Calculator plugin registered")