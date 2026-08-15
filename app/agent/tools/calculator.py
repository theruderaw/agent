import ast
import operator


_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def calculator(expression: str, precise: bool = False) -> float:
    """
    Evaluate a basic arithmetic expression.

    precise:
        False (default) - round the result to 2 decimal places, which also
        cleans up floating-point noise like 26.939999999999998 -> 26.94.
        True - return the full, unrounded result.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError:
        raise ValueError("Invalid expression")

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)

        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value

        if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            return _OPERATORS[type(node.op)](left, right)

        raise ValueError("Invalid expression")

    result = evaluate(tree)

    if not precise:
        result = round(result, 2)

    return result