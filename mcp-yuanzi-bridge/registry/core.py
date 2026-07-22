"""注册中心核心：提交、审核、状态流转、查询与行转换。

由 registry.py 拆分而来（ISOLATION_HARDENING_PLAN 加固1），纯结构移动，逻辑零变化。
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from .audit import _audit
from .hashing import compute_content_hash, compute_identity_hash, compute_signature
from .schema import REGISTRY_TABLE, RESERVED_PREFIXES, VERSIONS_TABLE, now_iso


# ---------------------------------------------------------------------------
# P0-B：注册验证（JSON Schema）+ 副作用标签（DESIGN_ATOM_FOUNDATION_V2 §2/§6）
# ---------------------------------------------------------------------------

# 仓库根 atom-registry-schema.json 是唯一 schema 权威（P0-A 同步维护 I/O 枚举）
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "atom-registry-schema.json"

# 副作用标签（跨代理定稿契约，不得改名）：
# 字段名 side_effect，枚举 ["pure", "impure"]，缺省 "impure"
SIDE_EFFECT_PURE = "pure"
SIDE_EFFECT_IMPURE = "impure"
SIDE_EFFECT_VALUES = (SIDE_EFFECT_PURE, SIDE_EFFECT_IMPURE)
DEFAULT_SIDE_EFFECT = SIDE_EFFECT_IMPURE

# 14 个内置基础原子的副作用标签常量表（基础原子不入注册表，标签走常量）。
# 文档只点名 math-calc / string-split / json-parse 为 pure（无副作用、无状态，
# 可安全并行/重试/缓存）；其余一律保守标 impure——含 string-match、
# hash-digest、date-time 与 ai。
BASE_ATOM_SIDE_EFFECTS: Dict[str, str] = {
    "system.math-calc": SIDE_EFFECT_PURE,
    "system.string-split": SIDE_EFFECT_PURE,
    "system.json-parse": SIDE_EFFECT_PURE,
    "system.file-read": SIDE_EFFECT_IMPURE,
    "system.file-write": SIDE_EFFECT_IMPURE,
    "system.file-dir": SIDE_EFFECT_IMPURE,
    "system.http-get": SIDE_EFFECT_IMPURE,
    "system.http-post": SIDE_EFFECT_IMPURE,
    "system.encrypt-aes": SIDE_EFFECT_IMPURE,
    "system.decrypt-aes": SIDE_EFFECT_IMPURE,
    "system.string-match": SIDE_EFFECT_IMPURE,
    "system.hash-digest": SIDE_EFFECT_IMPURE,
    "system.date-time": SIDE_EFFECT_IMPURE,
    "system.ai": SIDE_EFFECT_IMPURE,
}

# I/O 类型枚举（DESIGN_ATOM_FOUNDATION_V2 §2，类型名称统一小写）：
# json=结构化小数据（默认）/stream=流式不进内存/file_ref=对象存储 URL。
# schema 的 purpose.functions[].input_schema/output_schema 已带同款枚举
# （P0-A 同步维护），此处常量供 submit 兜底硬校验；缺失视为 json 不报错。
IO_TYPE_VALUES = ("json", "stream", "file_ref")
DEFAULT_IO_TYPE = "json"

# 分类扩展字段枚举（DESIGN_ATOM_FOUNDATION_V2 §3，全部可选）：
# 与 atom-registry-schema.json 的 classification 保持一致；style/audience/
# use_case 超上限或值不在枚举内拒绝注册，此处常量同样供兜底硬校验。
STYLE_VALUES = (
    "极简", "可靠", "专业", "优雅", "强大", "轻量",
    "创意", "温馨", "硬核", "极客", "玩趣", "实验",
)
AUDIENCE_VALUES = (
    "后端开发", "前端开发", "数据工程", "设计师", "作家", "学生",
    "所有人", "极客", "运维", "研究员", "创作者",
)
USE_CASE_VALUES = (
    "日常工作", "生产环境", "学习", "原型开发", "创意项目", "紧急救火",
)
QUALITY_VALUES = (
    "experimental", "functional", "polished", "battle-tested", "handcrafted",
)
DEFAULT_QUALITY = "functional"
# style/audience/use_case 数组上限（§3：最多 3 个）
CLASSIFICATION_LIST_LIMIT = 3
# use_case 中表示生产环境的取值（experimental 冲突警告用）
USE_CASE_PRODUCTION = "生产环境"
# narrative 占位词（§3：test/测试/123/todo，大小写不敏感）
NARRATIVE_PLACEHOLDER_WORDS = ("test", "测试", "123", "todo")

# 模块级缓存编译后的校验器；False 为负缓存（加载失败，退化为不校验）
_META_VALIDATOR: Any = None


def _get_meta_validator() -> Any:
    """加载 atom-registry-schema.json 并编译 Draft7 校验器（模块级缓存编译）。

    schema 文件缺失或解析失败时返回 None——注册主流程不因环境缺文件
    而整体崩溃（与 notarize 钩子"失败不影响主流程"的思路一致）。
    """
    global _META_VALIDATOR
    if _META_VALIDATOR is None:
        try:
            import jsonschema  # 惰性导入：register_mcp_atoms.py 同款依赖

            schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
            _META_VALIDATOR = jsonschema.Draft7Validator(schema)
        except Exception:  # noqa: BLE001 - 缺文件/坏 schema 时降级为不校验
            _META_VALIDATOR = False
    return _META_VALIDATOR or None


def _is_legacy_tolerated(error: Any) -> bool:
    """存量兼容窗口（P0）：四类历史欠账本轮不拦截，待存量 meta 补齐后收紧。

    现有注册流程从未接过 schema 校验（审计发现 validate 只跑在批量脚本），
    存量 meta 与测试 fixture 普遍缺以下字段，硬拒会误伤全部存量写入：

    1. purpose.summary 缺失
    2. purpose.functions[].description 缺失
    3. architecture.interface 缺失
    4. architecture.type 历史取值（如 python_script）不在 v2 枚举内
    """
    path = tuple(error.absolute_path)
    if error.validator == "required":
        # 缺字段错误的信息固定为 "'<name>' is a required property"
        parts = error.message.split("'")
        missing = parts[1] if len(parts) > 1 else ""
        if path == ("purpose",) and missing == "summary":
            return True
        if path[:2] == ("purpose", "functions") and missing == "description":
            return True
        if path == ("architecture",) and missing == "interface":
            return True
    if error.validator == "enum" and path == ("architecture", "type"):
        return True
    return False


def validate_atom_meta(atom: Dict[str, Any]) -> List[str]:
    """按仓库根 atom-registry-schema.json 校验入参 meta（P0-B 注册验证接线）。

    返回人类可读错误列表（"字段路径: 原因"，与 register_mcp_atoms.validate_atom
    同款格式），空列表表示通过；兼容窗口内的存量欠账不拦截。
    """
    errors: List[str] = []
    validator = _get_meta_validator()
    if validator is not None:
        for error in sorted(validator.iter_errors(atom), key=lambda e: list(e.path)):
            if _is_legacy_tolerated(error):
                continue
            loc = ".".join(str(p) for p in error.absolute_path) or "(root)"
            errors.append(f"{loc}: {error.message}")
    # 副作用标签枚举硬校验（schema 由 P0-A 同步加入，此处兜底双保险）
    side_effect = atom.get("side_effect")
    if side_effect is not None and side_effect not in SIDE_EFFECT_VALUES:
        errors.append(
            f"side_effect: {side_effect!r} is not one of {list(SIDE_EFFECT_VALUES)}"
        )
    # I/O 类型枚举硬校验（DESIGN_ATOM_FOUNDATION_V2 §2）：type 存在时必须是
    # json/stream/file_ref 严格小写三值之一，非法值拒绝注册；缺失视为 json
    # 不报错。schema 已带同款枚举，此处兜底双保险（校验器降级时仍能拦截）。
    purpose = atom.get("purpose")
    if isinstance(purpose, dict):
        functions = purpose.get("functions")
        if isinstance(functions, list):
            for index, func in enumerate(functions):
                if not isinstance(func, dict):
                    continue
                for io_field in ("input_schema", "output_schema"):
                    io_schema = func.get(io_field)
                    if not isinstance(io_schema, dict):
                        continue
                    io_type = io_schema.get("type")
                    if io_type is not None and io_type not in IO_TYPE_VALUES:
                        errors.append(
                            f"purpose.functions.{index}.{io_field}.type: "
                            f"{io_type!r} is not one of {list(IO_TYPE_VALUES)}"
                        )
    # 分类扩展字段硬校验（DESIGN_ATOM_FOUNDATION_V2 §3）：style/audience/
    # use_case 超上限（3 个）或值不在枚举内 → 拒绝注册。
    # schema 已带同款 maxItems/enum，此处兜底双保险。
    classification = atom.get("classification")
    if isinstance(classification, dict):
        for list_field, values in (
            ("style", STYLE_VALUES),
            ("audience", AUDIENCE_VALUES),
            ("use_case", USE_CASE_VALUES),
        ):
            items = classification.get(list_field)
            if not isinstance(items, list):
                continue
            if len(items) > CLASSIFICATION_LIST_LIMIT:
                errors.append(
                    f"classification.{list_field}: {items!r} has more than "
                    f"{CLASSIFICATION_LIST_LIMIT} items"
                )
            for item in items:
                if item not in values:
                    errors.append(
                        f"classification.{list_field}: "
                        f"{item!r} is not one of {list(values)}"
                    )
    return errors


def classification_warnings(atom: Dict[str, Any]) -> List[str]:
    """分类扩展字段警告规则（DESIGN_ATOM_FOUNDATION_V2 §3，不阻塞注册）。

    - narrative 与 description 完全一致 → 警告；
    - narrative 含占位词（test/测试/123/todo，大小写不敏感）→ 警告；
    - quality=handcrafted → 警告（提示需 Audit 审核）；
    - quality=experimental 且 use_case 含生产环境 → 冲突警告。

    返回人类可读警告列表，空列表表示无警告；submit_atom 随返回值透出并写入审计。
    """
    warnings: List[str] = []
    classification = atom.get("classification")
    if not isinstance(classification, dict):
        return warnings
    narrative = classification.get("narrative")
    if isinstance(narrative, str) and narrative:
        if narrative == atom.get("description"):
            warnings.append(
                "classification.narrative: 与 description 完全一致，"
                "叙事应补充而非复述简介"
            )
        lowered = narrative.lower()
        hits = [w for w in NARRATIVE_PLACEHOLDER_WORDS if w.lower() in lowered]
        if hits:
            warnings.append(
                f"classification.narrative: 含占位词 {hits}，请手写真实叙事"
            )
    quality = classification.get("quality")
    if quality == "handcrafted":
        warnings.append(
            "classification.quality: 'handcrafted' 需 Audit 审核确认"
        )
    use_case = classification.get("use_case")
    if (
        quality == "experimental"
        and isinstance(use_case, list)
        and USE_CASE_PRODUCTION in use_case
    ):
        warnings.append(
            "classification.quality: 'experimental' 与 use_case "
            f"'{USE_CASE_PRODUCTION}' 冲突，请调整品质等级或使用场景"
        )
    return warnings


def resolve_side_effect(atom: Dict[str, Any]) -> str:
    """解析原子的副作用标签：基础原子取常量表，注册原子取 meta，缺省 impure。

    注册原子在 submit_atom 归一化时已把 side_effect 镜像进 classification
    （注册表无独立列，DDL 归 migrations/*.sql 权威，本轮不改），
    读回时据此提升为顶层字段。

    取值优先级：常量表 → 顶层 side_effect（定稿契约位置，同 CLI 模板）
    → meta.side_effect（schema v2.1 的嵌套写法，宽容兼容）→ classification 镜像。
    """
    atom_id = atom.get("atom_id", "")
    if atom_id in BASE_ATOM_SIDE_EFFECTS:
        return BASE_ATOM_SIDE_EFFECTS[atom_id]
    value = atom.get("side_effect")
    if value is None:
        meta = atom.get("meta")
        if isinstance(meta, dict):
            value = meta.get("side_effect")
    if value is None:
        classification = atom.get("classification") or {}
        value = classification.get("side_effect")
    return value if value in SIDE_EFFECT_VALUES else DEFAULT_SIDE_EFFECT


def _insert_or_update(
    conn: sqlite3.Connection, atom: Dict[str, Any], signature: str, actor: str
) -> Dict[str, Any]:
    now = now_iso()
    lifecycle = atom.get("lifecycle", {})
    if "submitted_at" not in lifecycle:
        lifecycle["submitted_at"] = now
    if "created_at" not in lifecycle:
        lifecycle["created_at"] = now
    if "updated_at" not in lifecycle:
        lifecycle["updated_at"] = now

    ownership = atom.get("ownership", {})
    classification = atom.get("classification", {})
    compliance = atom.get("compliance", {})
    quality = atom.get("quality", {})
    runtime = atom.get("runtime", {})
    alias = atom.get("alias", [])

    signature_info = atom.get("signature", {})
    conn.execute(
        f"""
        INSERT INTO {REGISTRY_TABLE}
        (atom_id, name, version, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, lifecycle_json, signature_hash, signature_algorithm,
         content_hash, identity_hash, alias,
         created_at, submitted_at, registered_at, updated_at, version_counter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(atom_id) DO UPDATE SET
            name=excluded.name,
            version=excluded.version,
            description=excluded.description,
            purpose_json=excluded.purpose_json,
            architecture_json=excluded.architecture_json,
            ownership_json=excluded.ownership_json,
            classification_json=excluded.classification_json,
            compliance_json=excluded.compliance_json,
            quality_json=excluded.quality_json,
            runtime_json=excluded.runtime_json,
            lifecycle_json=excluded.lifecycle_json,
            signature_hash=excluded.signature_hash,
            content_hash=excluded.content_hash,
            identity_hash=excluded.identity_hash,
            alias=excluded.alias,
            updated_at=excluded.updated_at,
            version_counter=atom_registry.version_counter + 1
        """,
        (
            atom["atom_id"],
            atom.get("name", ""),
            atom.get("version", "1.0.0"),
            atom.get("description", ""),
            json.dumps(atom.get("purpose", {}), ensure_ascii=False),
            json.dumps(atom.get("architecture", {}), ensure_ascii=False),
            json.dumps(ownership, ensure_ascii=False),
            json.dumps(classification, ensure_ascii=False),
            json.dumps(compliance, ensure_ascii=False),
            json.dumps(quality, ensure_ascii=False),
            json.dumps(runtime, ensure_ascii=False),
            json.dumps(lifecycle, ensure_ascii=False),
            signature,
            "sha256",
            signature_info.get("content_hash", ""),
            signature_info.get("identity_hash", ""),
            json.dumps(alias, ensure_ascii=False),
            lifecycle.get("created_at"),
            lifecycle.get("submitted_at"),
            lifecycle.get("registered_at"),
            lifecycle.get("updated_at"),
        ),
    )
    conn.commit()
    return {
        "atom_id": atom["atom_id"],
        "signature": signature,
        "status": lifecycle.get("status", "submitted"),
    }


def _archive_version(
    conn: sqlite3.Connection, atom: Dict[str, Any], signature: str
) -> None:
    """把本次提交的内容快照归档到 atom_versions（同版本重复提交则更新）。"""
    now = now_iso()
    signature_info = atom.get("signature", {})
    existing = conn.execute(
        f"SELECT created_at FROM {VERSIONS_TABLE} WHERE atom_id = ? AND version = ?",
        (atom["atom_id"], atom.get("version", "1.0.0")),
    ).fetchone()
    created_at = existing[0] if existing else now
    conn.execute(
        f"""
        INSERT INTO {VERSIONS_TABLE}
        (atom_id, version, name, description, purpose_json, architecture_json,
         ownership_json, classification_json, compliance_json, quality_json,
         runtime_json, signature_hash, content_hash, identity_hash, changelog,
         created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(atom_id, version) DO UPDATE SET
            name=excluded.name,
            description=excluded.description,
            purpose_json=excluded.purpose_json,
            architecture_json=excluded.architecture_json,
            ownership_json=excluded.ownership_json,
            classification_json=excluded.classification_json,
            compliance_json=excluded.compliance_json,
            quality_json=excluded.quality_json,
            runtime_json=excluded.runtime_json,
            signature_hash=excluded.signature_hash,
            content_hash=excluded.content_hash,
            identity_hash=excluded.identity_hash,
            changelog=excluded.changelog,
            updated_at=excluded.updated_at
        """,
        (
            atom["atom_id"],
            atom.get("version", "1.0.0"),
            atom.get("name", ""),
            atom.get("description", ""),
            json.dumps(atom.get("purpose", {}), ensure_ascii=False),
            json.dumps(atom.get("architecture", {}), ensure_ascii=False),
            json.dumps(atom.get("ownership", {}), ensure_ascii=False),
            json.dumps(atom.get("classification", {}), ensure_ascii=False),
            json.dumps(atom.get("compliance", {}), ensure_ascii=False),
            json.dumps(atom.get("quality", {}), ensure_ascii=False),
            json.dumps(atom.get("runtime", {}), ensure_ascii=False),
            signature,
            signature_info.get("content_hash", ""),
            signature_info.get("identity_hash", ""),
            atom.get("changelog", ""),
            created_at,
            now,
        ),
    )
    conn.commit()


def submit_atom(
    conn: sqlite3.Connection, atom: Dict[str, Any], actor: str = "system"
) -> Dict[str, Any]:
    """提交一个新原子进入审核队列。"""
    atom_id = atom.get("atom_id", "")
    if not atom_id:
        raise ValueError("atom_id is required")

    # 保护内置命名空间（ISOLATION_HARDENING_PLAN 加固4）
    for prefix in RESERVED_PREFIXES:
        if atom_id.startswith(prefix):
            return {
                "success": False,
                "error": "reserved_namespace",
                "message": f"'{prefix}*' is reserved for built-in atoms",
            }

    signature = atom.get("signature", {}).get("hash") or compute_signature(atom)
    content_hash = compute_content_hash(atom)
    identity_hash = compute_identity_hash(atom)

    # 检查同 signature 是否被其他 atom_id 占用
    row = conn.execute(
        f"SELECT atom_id FROM {REGISTRY_TABLE} WHERE signature_hash = ?", (signature,)
    ).fetchone()
    if row and row[0] != atom_id:
        return {
            "success": False,
            "error": "duplicate_signature",
            "message": f"Signature already registered by atom '{row[0]}'; cannot register '{atom_id}'",
        }

    # BUG-006/016：能力级去重——content_hash 相同但 atom_id 不同，
    # 说明是换皮重复注册，拒绝。
    row = conn.execute(
        f"SELECT atom_id FROM {REGISTRY_TABLE} WHERE content_hash = ?",
        (content_hash,),
    ).fetchone()
    if row and row[0] != atom_id:
        return {
            "success": False,
            "error": "duplicate_signature",
            "message": (
                f"Identical capabilities already registered by atom "
                f"'{row[0]}'; cannot register '{atom_id}'"
            ),
        }

    lifecycle = atom.get("lifecycle", {})
    old_status = None
    existing = conn.execute(
        f"SELECT lifecycle_json FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if existing:
        old_status = json.loads(existing[0]).get("status")

    lifecycle["status"] = "submitted"
    atom["lifecycle"] = lifecycle
    if "signature" not in atom:
        atom["signature"] = {}
    atom["signature"]["hash"] = signature
    atom["signature"]["algorithm"] = "sha256"
    atom["signature"]["source"] = "auto-computed"
    atom["signature"]["content_hash"] = content_hash
    atom["signature"]["identity_hash"] = identity_hash

    # P0-B：注册接入 JSON Schema 校验（审计发现 submit_atom 从未接线 validate）。
    # 放在签名/生命周期自动补全之后、落库之前；失败返回错误 dict，不抛出。
    errors = validate_atom_meta(atom)
    if errors:
        return {
            "success": False,
            "error": "schema_validation",
            "message": "; ".join(errors),
            "errors": errors,
        }

    # P0-B：副作用标签归一化——meta 缺 side_effect 时默认写入 impure；
    # 注册表无独立列（DDL 归 migrations/*.sql 权威，本轮不改），
    # 镜像进 classification_json 持久化，读回由 resolve_side_effect 提升。
    atom["side_effect"] = atom.get("side_effect") or DEFAULT_SIDE_EFFECT
    atom.setdefault("classification", {})["side_effect"] = atom["side_effect"]

    # 连接原子（DESIGN_CONNECTOR_ATOM.md §四）：implements / compatibility / io /
    # schema_version / preferred 为顶层可选字段，注册表无独立列，与 side_effect
    # 同款处理——镜像进 classification_json 持久化；审核时据此做 implements 校验
    # （review_atom），设备匹配时据此做 compatibility 过滤与 schema_version /
    # preferred 排序（connectors.match_connector）。
    # 未声明这些字段的普通原子完全不受影响。
    for _connector_key in ("implements", "compatibility", "io", "schema_version", "preferred"):
        if atom.get(_connector_key) is not None:
            atom["classification"][_connector_key] = atom[_connector_key]

    result = _insert_or_update(conn, atom, signature, actor)
    _archive_version(conn, atom, signature)
    # 分类扩展字段警告（DESIGN_ATOM_FOUNDATION_V2 §3）：不阻塞注册，
    # 随返回 dict 的 "warnings" 键透出（无警告为空列表），并写入审计 detail。
    warnings = classification_warnings(atom)
    audit_detail = f"signature={signature}"
    if warnings:
        audit_detail += "; warnings: " + " | ".join(warnings)
    _audit(
        conn,
        atom_id,
        "submit",
        old_status,
        "submitted",
        actor,
        audit_detail,
    )
    result["success"] = True
    result["warnings"] = warnings
    return result


# 触发公证的 category 集合（DESIGN_ATOM_NOTARIZATION.md §二）。
# 设计文档的 soul 规则（soul.narrative 与 soul.style 均非空）未实现：
# atom-registry-schema.json 的 classification 只有 category/domain/tags/maturity，
# 全仓库无任何 soul 数据与读写代码，该规则无输入可判定，故只保留 category 集合。
NOTARIZE_CATEGORIES = frozenset({"asset", "artwork", "service"})


# ---------------------------------------------------------------------------
# 连接原子：implements 接口标准校验（DESIGN_CONNECTOR_ATOM.md §四）
# ---------------------------------------------------------------------------
#
# 契约（钉死，不得偏离）：
# - implements 为顶层可选字符串，值是接口标准原子的 atom_id（如 schema.location-v1）；
# - 接口标准原子必须存在且 architecture.type == "schema"，
#   否则拒绝，reason 以 implements_unknown_schema 开头；
# - 连接器声明的输出必须覆盖标准定义的全部键且类型一致（按 JSON 类型名字符串
#   比较：number/string/array/object/boolean/integer），
#   否则拒绝，reason 以 implements_mismatch 开头；
# - 未声明 implements 的原子零影响。

# output_schema 中属于 I/O 元信息的保留键（atom-registry-schema.json 定义），
# 提取输出字段时跳过，不当作输出键。
_OUTPUT_SCHEMA_META_KEYS = frozenset(
    {"type", "description", "default", "required", "title", "properties"}
)


def _extract_output_fields(output_schema: Any) -> Dict[str, str]:
    """从 purpose.functions[].output_schema 提取 字段名 -> JSON 类型名。

    兼容两种写法：
    - JSON Schema 风格：{"type": "object", "properties": {f: {"type": t}}}；
    - 扁平风格：{f: t}（t 为类型名字符串，保留键除外）。
    类型名统一转小写后比较。
    """
    fields: Dict[str, str] = {}
    if not isinstance(output_schema, dict):
        return fields
    properties = output_schema.get("properties")
    if isinstance(properties, dict):
        for key, spec in properties.items():
            if isinstance(spec, dict) and isinstance(spec.get("type"), str):
                fields[key] = spec["type"].lower()
            elif isinstance(spec, str):
                fields[key] = spec.lower()
    for key, value in output_schema.items():
        if key in _OUTPUT_SCHEMA_META_KEYS:
            continue
        if isinstance(value, str):
            fields[key] = value.lower()
    return fields


def _extract_output_contract(atom: Dict[str, Any]) -> Dict[str, str]:
    """读取原子声明的输出契约（字段名 -> JSON 类型名）。

    取值优先级（以 atom-registry-schema.json 实际支持的字段为准）：
    purpose.functions[].output_schema 优先；全部为空时回退顶层 io.output
    （DESIGN_CONNECTOR_ATOM §四的写法，submit 时已镜像进
    classification.io）。入参 atom 只需含 purpose / classification 两个键。
    """
    purpose = atom.get("purpose") or {}
    functions = purpose.get("functions")
    if isinstance(functions, list):
        for func in functions:
            if isinstance(func, dict):
                fields = _extract_output_fields(func.get("output_schema"))
                if fields:
                    return fields
    classification = atom.get("classification") or {}
    io_info = classification.get("io")
    if isinstance(io_info, dict):
        output = io_info.get("output")
        if isinstance(output, dict):
            return {
                key: value.lower()
                for key, value in output.items()
                if isinstance(value, str)
            }
    return {}


def _validate_implements(
    conn: sqlite3.Connection, atom_id: str, atom: Dict[str, Any]
) -> Optional[str]:
    """审核挂点：连接器声明 implements 时校验其与接口标准的一致性。

    返回 None 表示通过（或未声明 implements——普通原子零影响）；
    返回拒绝原因字符串（implements_unknown_schema / implements_mismatch 开头）。
    只读查询，不写库；任何解析异常按校验失败处理（保守拒绝）。
    """
    classification = atom.get("classification") or {}
    implements = classification.get("implements")
    if not isinstance(implements, str) or not implements:
        return None

    row = conn.execute(
        f"SELECT purpose_json, architecture_json, classification_json "
        f"FROM {REGISTRY_TABLE} WHERE atom_id = ?",
        (implements,),
    ).fetchone()
    if not row:
        return f"implements_unknown_schema: schema atom '{implements}' not found"

    architecture = json.loads(row[1]) if row[1] else {}
    if architecture.get("type") != "schema":
        return (
            f"implements_unknown_schema: atom '{implements}' is not an interface "
            f"standard (architecture.type={architecture.get('type')!r}, "
            f"expected 'schema')"
        )

    standard = _extract_output_contract(
        {
            "purpose": json.loads(row[0]) if row[0] else {},
            "classification": json.loads(row[2]) if row[2] else {},
        }
    )
    declared = _extract_output_contract(atom)

    missing = sorted(k for k in standard if k not in declared)
    mismatched = sorted(
        f"{k} (expected {standard[k]}, got {declared[k]})"
        for k in standard
        if k in declared and declared[k] != standard[k]
    )
    if missing or mismatched:
        parts = []
        if missing:
            parts.append("missing output keys: " + ", ".join(missing))
        if mismatched:
            parts.append("type mismatch: " + ", ".join(mismatched))
        return (
            f"implements_mismatch: connector '{atom_id}' does not satisfy "
            f"'{implements}' ({'; '.join(parts)})"
        )
    return None


def review_atom(
    conn: sqlite3.Connection,
    atom_id: str,
    approved: bool,
    reviewer: str = "system",
    comments: str = "",
    score: Optional[float] = None,
) -> Dict[str, Any]:
    """审核原子，通过后进入 registered 状态，拒绝进入 rejected 状态。"""
    row = conn.execute(
        f"SELECT lifecycle_json, classification_json, purpose_json FROM {REGISTRY_TABLE} WHERE atom_id = ?",
        (atom_id,),
    ).fetchone()
    if not row:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    lifecycle = json.loads(row[0])
    old_status = lifecycle.get("status")

    # 连接原子 implements 校验挂点（DESIGN_CONNECTOR_ATOM.md §四）：
    # 只拦截"批准"路径——声明了 implements 的连接器与接口标准不一致时
    # 强制转为拒绝，reason 以 implements_mismatch / implements_unknown_schema
    # 开头并写入 review_result.comments；未声明 implements 的原子零影响。
    reject_reason: Optional[str] = None
    if approved:
        reject_reason = _validate_implements(
            conn,
            atom_id,
            {
                "purpose": json.loads(row[2]) if row[2] else {},
                "classification": json.loads(row[1]) if row[1] else {},
            },
        )
        if reject_reason:
            approved = False
            comments = reject_reason

    if approved:
        lifecycle["status"] = "registered"
        lifecycle["registered_at"] = now_iso()
        lifecycle["review_result"] = {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "comments": comments,
            "score": score,
        }
    else:
        lifecycle["status"] = "rejected"
        lifecycle["review_result"] = {
            "reviewer": reviewer,
            "reviewed_at": now_iso(),
            "comments": comments,
            "score": score,
        }

    lifecycle["updated_at"] = now_iso()
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ?, reviewed_at = ?, reviewed_by = ?, review_comments = ?, review_score = ? WHERE atom_id = ?",
        (
            json.dumps(lifecycle, ensure_ascii=False),
            lifecycle["review_result"]["reviewed_at"],
            reviewer,
            comments,
            score,
            atom_id,
        ),
    )
    conn.commit()
    _audit(conn, atom_id, "review", old_status, lifecycle["status"], reviewer, comments)
    # 原子公证钩子（DESIGN_ATOM_NOTARIZATION.md §二/§五）：
    # 审核通过且 category 属于 NOTARIZE_CATEGORIES 的原子自动上链，
    # 默认后台线程执行、注册不阻塞；公证的任何失败都不影响审核结果本身。
    if lifecycle["status"] == "registered":
        classification = json.loads(row[1]) if row[1] else {}
        if classification.get("category") in NOTARIZE_CATEGORIES:
            _trigger_notarize_on_register(conn, atom_id, reviewer)
    result: Dict[str, Any] = {
        "success": True,
        "atom_id": atom_id,
        "status": lifecycle["status"],
    }
    if reject_reason:
        result["reason"] = reject_reason
    return result


# 置 1 时公证同步执行（测试确定性）；默认后台 daemon 线程，注册不阻塞
NOTARIZE_SYNC_ENV = "YUANZI_NOTARIZE_SYNC"


def _trigger_notarize_on_register(
    conn: sqlite3.Connection, atom_id: str, reviewer: str
) -> None:
    """审核通过后触发符合条件原子的链上公证（DESIGN_ATOM_NOTARIZATION.md §二/§五）。

    - 默认在后台 daemon 线程中用新连接执行，注册流程不阻塞；
    - YUANZI_NOTARIZE_SYNC=1 时在当前连接上同步执行（测试确定性）；
    - notarize 模块缺失或公证过程的任何异常都吞掉，绝不影响审核结果。
    """
    try:
        import notarize  # 惰性导入，降低耦合（同 auth.py 里 from registry import _audit 的模式）
    except Exception:  # noqa: BLE001 - 模块未落盘时静默跳过，不影响审核
        return

    def _run(target_conn: sqlite3.Connection) -> None:
        try:
            notarize.notarize_atom(target_conn, atom_id, "register", actor=reviewer)
        except Exception:  # noqa: BLE001 - 公证失败绝不影响审核结果
            pass

    if os.environ.get(NOTARIZE_SYNC_ENV) == "1":
        _run(conn)
        return

    # sqlite 连接不宜跨线程共享，后台线程新开连接；
    # 无文件库（:memory: 等）无法开新连接，退化为同步执行
    db_path = ""
    try:
        for db_row in conn.execute("PRAGMA database_list").fetchall():
            if db_row[1] == "main":
                db_path = db_row[2]
                break
    except Exception:  # noqa: BLE001
        db_path = ""
    if not db_path:
        _run(conn)
        return

    def _background() -> None:
        try:
            bg_conn = sqlite3.connect(db_path)
            bg_conn.row_factory = sqlite3.Row
        except Exception:  # noqa: BLE001 - 连接失败只损失公证，不影响审核
            return
        try:
            _run(bg_conn)
        finally:
            bg_conn.close()

    threading.Thread(target=_background, daemon=True).start()


# 统一的状态流转表：set_atom_status 与 probe_atom 的唯一事实来源（BUG-019）
ALLOWED_TRANSITIONS = {
    "registered": ["probing", "running", "unreachable", "offline", "deprecated"],
    "probing": ["running", "unreachable", "offline", "deprecated"],
    "running": ["probing", "unreachable", "offline", "deprecated", "registered"],
    "unreachable": ["probing", "running", "offline", "deprecated"],
    "offline": ["probing", "running", "unreachable", "deprecated", "registered"],
    "deprecated": ["registered"],
}


def _transition_allowed(old_status: Optional[str], new_status: str) -> bool:
    return new_status in ALLOWED_TRANSITIONS.get(old_status or "", [])


def set_atom_status(
    conn: sqlite3.Connection,
    atom_id: str,
    status: str,
    actor: str = "system",
    detail: str = "",
) -> Dict[str, Any]:
    """在注册后变更原子运行状态：running / offline / deprecated。"""
    row = conn.execute(
        f"SELECT lifecycle_json FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return {
            "success": False,
            "error": "not_found",
            "message": f"Atom '{atom_id}' not found",
        }

    lifecycle = json.loads(row[0])
    old_status = lifecycle.get("status")
    if not _transition_allowed(old_status, status):
        return {
            "success": False,
            "error": "invalid_transition",
            "message": f"Cannot transition from '{old_status}' to '{status}'",
        }

    lifecycle["status"] = status
    lifecycle["updated_at"] = now_iso()
    conn.execute(
        f"UPDATE {REGISTRY_TABLE} SET lifecycle_json = ?, "
        "version_counter = version_counter + 1 WHERE atom_id = ?",
        (json.dumps(lifecycle, ensure_ascii=False), atom_id),
    )
    conn.commit()
    _audit(conn, atom_id, "status_change", old_status, status, actor, detail)
    return {
        "success": True,
        "atom_id": atom_id,
        "old_status": old_status,
        "new_status": status,
    }


def get_atom(conn: sqlite3.Connection, atom_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        f"SELECT * FROM {REGISTRY_TABLE} WHERE atom_id = ?", (atom_id,)
    ).fetchone()
    if not row:
        return None
    return _row_to_atom(row)


def list_atoms(
    conn: sqlite3.Connection,
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    query = f"SELECT * FROM {REGISTRY_TABLE} WHERE 1=1"
    params: List[Any] = []
    if status:
        query += " AND json_extract(lifecycle_json, '$.status') = ?"
        params.append(status)
    if category:
        query += " AND json_extract(classification_json, '$.category') = ?"
        params.append(category)
    if search:
        query += " AND (atom_id LIKE ? OR name LIKE ? OR alias LIKE ?)"
        params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
    query += " ORDER BY atom_id"
    rows = conn.execute(query, params).fetchall()
    return [_row_to_atom(row) for row in rows]


def _row_to_atom(row: sqlite3.Row) -> Dict[str, Any]:
    keys = [k for k in row.keys()]
    atom: Dict[str, Any] = {}
    for k in keys:
        v = row[k]
        if k.endswith("_json") and v is not None:
            atom[k[:-5]] = json.loads(v)
        elif k == "alias" and v is not None:
            atom[k] = json.loads(v)
        else:
            atom[k] = v
    return atom
