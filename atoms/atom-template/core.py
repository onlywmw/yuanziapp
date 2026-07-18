# core.py
# TODO: 替换为当前原子的核心逻辑

def handler(data):
    """
    原子的核心处理函数
    :param data: dict, 调用方传入的参数
    :return: dict, 标准输出格式 {"status": "success", "data": {...}} 或 {"status": "error", "message": "..."}
    """
    try:
        # ===== 在这里写你的核心逻辑 =====
        result = data
        # ================================
        return {
            "status": "success",
            "data": result
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
