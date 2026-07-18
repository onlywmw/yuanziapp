# core.py
def handler(data):
    """
    原子的核心处理函数
    :param data: dict, 例如 {"a": 10, "b": 20}
    :return: dict, 例如 {"status": "success", "data": {"result": 30}}
    """
    try:
        num_a = float(data.get("a", 0))
        num_b = float(data.get("b", 0))
        result = num_a + num_b
        return {
            "status": "success",
            "data": {
                "result": result
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
