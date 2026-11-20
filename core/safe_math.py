from __future__ import annotations

import ast
import math
import operator


class CalculationError(ValueError):
    """Expressão matemática inválida ou fora dos limites permitidos."""


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
MAX_EXPRESSION_LENGTH = 200
MAX_AST_NODES = 64
MAX_ABS_RESULT = 1e100
MAX_ABS_EXPONENT = 100


def safe_calculate(expression: str) -> int | float:
    """Avalia apenas aritmética numérica; nomes, chamadas e atributos são negados."""
    if not isinstance(expression, str) or not expression.strip():
        raise CalculationError("Digite uma expressão matemática.")
    expression = expression.strip()
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise CalculationError("A expressão ultrapassa 200 caracteres.")
    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise CalculationError("Expressão matemática inválida.") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise CalculationError("A expressão é complexa demais.")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            value = node.value
            if abs(value) > MAX_ABS_RESULT:
                raise CalculationError("Número fora dos limites.")
            return value
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _bounded(_UNARY_OPERATORS[type(node.op)](evaluate(node.operand)))
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > MAX_ABS_EXPONENT:
                raise CalculationError("O expoente deve ficar entre -100 e 100.")
            try:
                return _bounded(_BINARY_OPERATORS[type(node.op)](left, right))
            except ZeroDivisionError as exc:
                raise CalculationError("Não é possível dividir por zero.") from exc
            except (OverflowError, ValueError) as exc:
                raise CalculationError("O resultado excede os limites da calculadora.") from exc
        raise CalculationError("Operação não permitida. Use somente números e + − × ÷ parênteses.")

    return evaluate(tree)


def _bounded(value: int | float) -> int | float:  # noqa: PYI041 - preserve integer results instead of coercing them to float.
    if isinstance(value, complex) or not isinstance(value, (int, float)):
        raise CalculationError("A calculadora aceita somente resultados reais.")
    if isinstance(value, float) and not math.isfinite(value):
        raise CalculationError("O resultado não é finito.")
    if abs(value) > MAX_ABS_RESULT:
        raise CalculationError("O resultado excede o limite 10^100.")
    return value
