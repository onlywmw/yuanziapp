# core.py — system.math-calc 数学运算（基础原子，内置不可注册）
import ast
import math
import operator

# 允许的运算符（AST 安全求值，不使用 eval()）
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {
    name: getattr(math, name)
    for name in (
        "sqrt",
        "sin",
        "cos",
        "tan",
        "log",
        "log2",
        "log10",
        "exp",
        "floor",
        "ceil",
        "fabs",
    )
}
_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})
_CONSTS = {"pi": math.pi, "e": math.e}


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"unsupported constant: {node.value!r}")
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise ValueError(f"unknown name: {node.id}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        return _BIN_OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        func = _FUNCS.get(node.func.id)
        if not func:
            raise ValueError(f"unsupported function: {node.func.id}")
        if node.keywords:
            raise ValueError("keyword arguments not supported")
        return func(*[_eval(arg) for arg in node.args])
    raise ValueError(f"unsupported expression: {ast.dump(node)}")


def handler(data):
    """
    安全求值数学表达式
    :param data: {"expression": "2 + 3 * 4", "precision": 2}
    """
    try:
        expression = data.get("expression")
        if not expression:
            return {"status": "error", "message": "missing required field: expression"}
        result = _eval(ast.parse(str(expression), mode="eval"))
        precision = data.get("precision")
        if precision is not None:
            result = round(result, int(precision))
        return {"status": "success", "data": {"result": result}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
