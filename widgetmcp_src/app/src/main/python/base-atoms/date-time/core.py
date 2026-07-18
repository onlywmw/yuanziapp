# core.py — system.date-time 日期时间处理（基础原子，内置不可注册）
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _tz(name):
    if not name or name.upper() == "UTC":
        return timezone.utc
    return ZoneInfo(name)


def _parse(value):
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def handler(data):
    """
    日期时间处理
    :param data: {"action": "now"|"format"|"diff",
                  "value": "...", "value2": "...", "format": "%Y-%m-%d"|"ISO8601",
                  "timezone": "UTC"}
    """
    try:
        action = data.get("action", "now")
        tz = _tz(data.get("timezone", "UTC"))
        fmt = data.get("format", "ISO8601")

        if action == "now":
            return {
                "status": "success",
                "data": {"result": datetime.now(tz).isoformat()},
            }

        if action == "format":
            value = data.get("value")
            if not value:
                return {"status": "error", "message": "missing required field: value"}
            dt = _parse(value)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone(tz)
            result = dt.isoformat() if fmt == "ISO8601" else dt.strftime(fmt)
            return {"status": "success", "data": {"result": result}}

        if action == "diff":
            value, value2 = data.get("value"), data.get("value2")
            if not value or not value2:
                return {
                    "status": "error",
                    "message": "missing required field: value/value2",
                }
            delta = _parse(value2) - _parse(value)
            return {
                "status": "success",
                "data": {"result": delta.total_seconds(), "unit": "seconds"},
            }

        return {"status": "error", "message": f"unknown action: {action}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
