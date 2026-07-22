"""连接原子自动匹配模块（设计来源：docs/DESIGN_CONNECTOR_ATOM.md §三「自动匹配」）。

连接原子 = 标准原子 + compatibility 字段 + implements 接口标准声明。本模块只负责
"为本设备找到最合适的连接器"这一段：

    用户引用某功能 (function=location/camera/bluetooth/storage/...)
      1. detect_device() 读本设备 os / os_version / manufacturer / hardware
      2. match_connector() 在注册中心搜候选连接器
      3. 按 compatibility 硬过滤（os 相等、os_version 满足约束、
         manufacturer 精确或 "*"、hardware 为子集）
      4. 排序：manufacturer 精确 > "*" → 评分高 → 使用人数多
      5. 返回前 limit 个候选，排第一的就是要自动安装的

零新基础设施：候选直接从现有 atom_registry 表查询，复用 registry/core.py
的查询惯例（json_extract(lifecycle_json, '$.status') 等），不新建连接。

设备信息来源（环境变量，缺省 None/空）：
    YUANZI_DEVICE_OS            例: android / ios / huawei / windows / linux
    YUANZI_DEVICE_OS_VERSION    例: "12"
    YUANZI_DEVICE_MANUFACTURER  例: samsung / xiaomi
    YUANZI_DEVICE_HARDWARE      逗号分隔，例: "gps,camera,bluetooth"

缺失设备字段的处理（本模块的统一约定）：某一项设备信息未知（None/空）时，
对应过滤项放行——"无法证伪即兼容"，避免在未配置环境变量的开发机上
匹配结果恒为空。四项硬过滤规则本身（契约 4）在双侧值都已知时严格生效。

生命周期口径（以 registry/core.py 实际状态枚举为准）：只统计
registered / running 两种"已注册/可用"状态；submitted / rejected /
probing / unreachable / offline / deprecated 一律不参与匹配。

compatibility 的落库位置：atom_registry 表只有
purpose/architecture/ownership/classification/compliance/quality/runtime/
lifecycle 这些 JSON 列（见 registry/core.py _insert_or_update），顶层
compatibility 随注册归一化镜像进 classification_json（与 side_effect 同款
镜像惯例）；读取时优先取 classification.compatibility。
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Optional

try:  # 与 api.py 同款导入惯例（mcp-yuanzi-bridge 在 sys.path 上时）
    from registry.schema import REGISTRY_TABLE
except Exception:  # noqa: BLE001 - 独立导入本模块时退化为字面量
    REGISTRY_TABLE = "atom_registry"


# ---------------------------------------------------------------------------
# 环境变量（契约 4）
# ---------------------------------------------------------------------------

ENV_DEVICE_OS = "YUANZI_DEVICE_OS"
ENV_DEVICE_OS_VERSION = "YUANZI_DEVICE_OS_VERSION"
ENV_DEVICE_MANUFACTURER = "YUANZI_DEVICE_MANUFACTURER"
ENV_DEVICE_HARDWARE = "YUANZI_DEVICE_HARDWARE"

# 只统计"已注册/可用"的原子（以 registry/core.py 实际状态枚举为准：
# registered = 审核通过；running = 探测在线。其余 submitted/rejected/
# probing/unreachable/offline/deprecated 不参与匹配）
AVAILABLE_STATUSES = ("registered", "running")

# manufacturer 通配值：不限厂商
MANUFACTURER_ANY = "*"


def _env_or_none(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def detect_device() -> Dict[str, Any]:
    """从环境变量读取本设备信息，缺省 None/空列表（契约 4）。

    返回 {"os": ..., "os_version": ..., "manufacturer": ..., "hardware": [...]}
    """
    raw_hardware = os.environ.get(ENV_DEVICE_HARDWARE) or ""
    hardware = [h.strip() for h in raw_hardware.split(",") if h.strip()]
    return {
        "os": _env_or_none(ENV_DEVICE_OS),
        "os_version": _env_or_none(ENV_DEVICE_OS_VERSION),
        "manufacturer": _env_or_none(ENV_DEVICE_MANUFACTURER),
        "hardware": hardware,
    }


# ---------------------------------------------------------------------------
# 版本约束比较（契约 4：支持 >=,>,<=,<,== 与裸版本号，按数字段比较）
# ---------------------------------------------------------------------------

_VERSION_OPS = (">=", "<=", "==", ">", "<")  # 注意：双字符算子必须先于单字符匹配
_DIGITS_RE = re.compile(r"\d+")


def _version_tuple(version: str) -> tuple:
    """把 "11" / "11.2.3" 解析成数字段元组；任一段无数字则返回空元组（无法解析）。"""
    parts: List[int] = []
    for segment in str(version).strip().split("."):
        match = _DIGITS_RE.match(segment.strip())
        if not match:
            return ()
        parts.append(int(match.group(0)))
    return tuple(parts)


def version_satisfies(version: str, constraint: str) -> bool:
    """判断 version 是否满足 constraint（契约 4）。

    - constraint 支持 ">="、">"、"<="、"<"、"==" 前缀与裸版本号（裸版本号按 == 处理）；
    - 按数字段逐段比较，短的一侧补 0（"11" 与 "11.0" 相等）；
    - constraint 为空/None 视为无约束，恒 True；version 为空/None 或任一侧
      无法解析出数字段时返回 False。
    """
    if constraint is None or not str(constraint).strip():
        return True
    if version is None or not str(version).strip():
        return False

    text = str(constraint).strip()
    op = "=="
    raw = text
    for prefix in _VERSION_OPS:
        if text.startswith(prefix):
            op = prefix
            raw = text[len(prefix):].strip()
            break

    left = _version_tuple(version)
    right = _version_tuple(raw)
    if not left or not right:
        return False

    width = max(len(left), len(right))
    left += (0,) * (width - len(left))
    right += (0,) * (width - len(right))

    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    return left == right


# ---------------------------------------------------------------------------
# 候选匹配（契约 4）
# ---------------------------------------------------------------------------


def _escape_like(value: str) -> str:
    """转义 LIKE 模式中的特殊字符（配合 ESCAPE '\\'）。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _extract_compatibility(classification: Dict[str, Any]) -> Dict[str, Any]:
    """从 classification 镜像中取 compatibility 字段（dict 以外一律视为无）。"""
    compat = classification.get("compatibility")
    return compat if isinstance(compat, dict) else {}


def _review_score(lifecycle: Dict[str, Any]) -> float:
    """排序分：lifecycle.review_result.score，缺省 0（契约 4）。"""
    review = lifecycle.get("review_result")
    if not isinstance(review, dict):
        return 0.0
    score = review.get("score")
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _usage_count(_classification: Dict[str, Any], _lifecycle: Dict[str, Any]) -> float:
    """使用人数：注册表数据模型（atom_registry 各 JSON 列，见 registry/core.py
    与 registry/schema.py 的 AtomRegistration）目前没有使用人数字段，
    按契约 4 用 0 兜底；排序键保留此位，将来补字段后仅需改本函数。
    """
    return 0.0


def match_connector(
    conn: sqlite3.Connection,
    function: str,
    device: Dict[str, Any],
    limit: int = 5,
) -> List[Dict[str, Any]]:
    """为指定功能在注册中心匹配最适合本设备的连接器候选（契约 4）。

    候选（满足其一）：
      - atom_id 以 "connector.{function}-" 开头；
      - classification.domain == function（大小写不敏感）。

    硬过滤（设备侧字段已知时才生效，未知放行——见模块 docstring 约定）：
      - compatibility.os 与 device.os 相等（大小写不敏感）；
      - device.os_version 满足 compatibility.os_version 约束；
      - compatibility.manufacturer 为精确值或 "*"；
      - compatibility.hardware ⊆ device.hardware。

    排序：manufacturer 精确匹配优先于 "*" → 评分高优先 → 使用人数多优先
    → atom_id 字典序（确定性兜底）。

    返回 [{"atom_id", "manufacturer_match": "exact"|"any", "score",
    "compatibility"}]，最多 limit 条。
    """
    device = device or {}
    dev_os = (device.get("os") or "").strip().lower() or None
    dev_os_version = device.get("os_version")
    dev_os_version = str(dev_os_version).strip() if dev_os_version is not None else ""
    dev_os_version = dev_os_version or None
    dev_manufacturer = (device.get("manufacturer") or "").strip().lower() or None
    raw_hw = device.get("hardware") or []
    dev_hardware = {str(h).strip().lower() for h in raw_hw if str(h).strip()}

    func = (function or "").strip()
    if not func:
        return []

    # 复用 registry/core.py 的查询惯例（json_extract 各 *_json 列），
    # 只取匹配所需的三列，不依赖连接的 row_factory。
    status_placeholders = ", ".join("?" for _ in AVAILABLE_STATUSES)
    query = f"""
        SELECT atom_id, classification_json, lifecycle_json
        FROM {REGISTRY_TABLE}
        WHERE (
            atom_id LIKE ? ESCAPE '\\'
            OR LOWER(json_extract(classification_json, '$.domain')) = ?
        )
        AND json_extract(lifecycle_json, '$.status') IN ({status_placeholders})
        ORDER BY atom_id
    """
    prefix_pattern = f"connector.{_escape_like(func)}-%"
    params: List[Any] = [prefix_pattern, func.lower(), *AVAILABLE_STATUSES]

    candidates: List[Dict[str, Any]] = []
    for row in conn.execute(query, params).fetchall():
        atom_id, classification_json, lifecycle_json = row[0], row[1], row[2]
        try:
            classification = json.loads(classification_json) if classification_json else {}
        except (TypeError, ValueError):
            classification = {}
        try:
            lifecycle = json.loads(lifecycle_json) if lifecycle_json else {}
        except (TypeError, ValueError):
            lifecycle = {}
        if not isinstance(classification, dict):
            classification = {}
        if not isinstance(lifecycle, dict):
            lifecycle = {}

        compat = _extract_compatibility(classification)

        # 硬过滤 1：os 相等（大小写不敏感）
        compat_os = str(compat.get("os") or "").strip().lower()
        if compat_os and dev_os and compat_os != dev_os:
            continue

        # 硬过滤 2：os_version 满足约束
        compat_os_version = compat.get("os_version")
        if compat_os_version and dev_os_version:
            if not version_satisfies(dev_os_version, str(compat_os_version)):
                continue

        # 硬过滤 3：manufacturer 精确或 "*"
        compat_manufacturer = str(compat.get("manufacturer") or "").strip().lower()
        exact_manufacturer = compat_manufacturer not in ("", MANUFACTURER_ANY)
        if exact_manufacturer and dev_manufacturer and compat_manufacturer != dev_manufacturer:
            continue
        manufacturer_match = (
            "exact"
            if exact_manufacturer and dev_manufacturer == compat_manufacturer
            else "any"
        )

        # 硬过滤 4：compatibility.hardware ⊆ device.hardware
        compat_hardware = {
            str(h).strip().lower()
            for h in (compat.get("hardware") or [])
            if str(h).strip()
        }
        if compat_hardware and dev_hardware and not compat_hardware.issubset(dev_hardware):
            continue

        candidates.append(
            {
                "atom_id": atom_id,
                "manufacturer_match": manufacturer_match,
                "score": _review_score(lifecycle),
                "compatibility": compat,
                # 排序专用键，不进返回值
                "_usage": _usage_count(classification, lifecycle),
            }
        )

    candidates.sort(
        key=lambda c: (
            0 if c["manufacturer_match"] == "exact" else 1,  # 精确 > "*"
            -c["score"],  # 评分高优先
            -c["_usage"],  # 使用人数多优先（当前恒 0，见 _usage_count 注释）
            c["atom_id"],  # 确定性兜底
        )
    )

    results: List[Dict[str, Any]] = []
    for item in candidates[: max(int(limit), 0)]:
        item = dict(item)
        item.pop("_usage", None)
        results.append(item)
    return results
