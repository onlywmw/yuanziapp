"""星云引擎主循环（DESIGN_NEBULA_ENGINE.md / DESIGN_ATOM_GRAVITY.md / DESIGN_RESONANCE_SPEC.md）。

定位：引擎是活的。每 30 秒一次主循环，五阶段：
采集 → 共振 → 聚类 → 输出 → 学习
（DESIGN_NEBULA_ENGINE §一原文为七步；本轮把"决策"并入"输出"、把"反馈"
作为学习的输入事件，对外呈现五阶段——与学习阶段由 feedback 驱动的口径一致）。

实现契约：
- 共振算法严格按 DESIGN_RESONANCE_SPEC §四：同类别 ×2、跨类别 ×0.5、
  维度权重缺省 0.5；纯 Python 双重循环，12 原子 × 5 维度 × 66 对 < 1ms。
- 权重学习按 §五：接受 +0.05、忽略 -0.03、沉默不调整，范围 [0.1, 0.9]，
  时间衰减（最近 7 天 ×1.0，7-30 天 ×0.7，30+ 天 ×0.3）。
- 输出克制按 DESIGN_NEBULA_ENGINE §六：集群与上一轮一致则不打扰，
  只在新集群出现时输出。
- 原子数据来源复用 registry.core.list_atoms（只读），不新造存储入口；
  学习产物（维度权重 / 有效模式）落 nebula 自建的两张表。
- 主循环可手动 step()，也可 start()/stop() 后台 daemon 线程跑
  （线程惯例同 registry.core._trigger_notarize_on_register：
  文件库后台线程新开连接，内存库退化为复用当前连接）。

建表口径（与任务约束的偏差说明）：新表本应按惯例走 migrations/*.sql
独立迁移文件，但 tests/test_migrations.py 与 tests/test_versions.py 硬编码了
迁移版本列表 [1..13]（只读文件），任何新迁移文件被 discover_migrations
发现即破坏存量测试基线。本轮改为模块内 ensure_nebula_schema() 惰性幂等建表
（CREATE TABLE IF NOT EXISTS，与迁移机制同款幂等语义），待后续统一收口时
可原样平移为 014_nebula.sql。

api.py 本轮不接线：对外只暴露模块级函数（collect_fields / compute_resonance /
resonance_map / cluster_from_resonances / learn_from_feedback / run_nebula_step）
与 NebulaEngine 类，待后续任务挂端点。
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from registry.core import list_atoms


# ---------------------------------------------------------------------------
# 常量（DESIGN_NEBULA_ENGINE §二 / DESIGN_RESONANCE_SPEC §四/§五）
# ---------------------------------------------------------------------------

# 主循环节奏：30 秒一次，不是实时（§二）。可注入，测试用 0 或手动 step()。
LOOP_INTERVAL_SECONDS = 30.0

# 聚类阈值：共振超过阈值的原子自然聚在一起（DESIGN_NEBULA_ENGINE §五）。
# 文档未给具体数值，取缺省 0.5，可注入。
CLUSTER_THRESHOLD = 0.5

# 共振公式因子（§四）：同类别 ×2，跨类别 ×0.5
SAME_CATEGORY_FACTOR = 2.0
CROSS_CATEGORY_FACTOR = 0.5

# 维度权重（§五）：初始 0.5，范围 [0.1, 0.9]
DEFAULT_WEIGHT = 0.5
WEIGHT_MIN = 0.1
WEIGHT_MAX = 0.9

# 学习步长（§五 / DESIGN_NEBULA_ENGINE §七）：接受 +0.05，忽略 -0.03
LEARN_ACCEPT_DELTA = 0.05
LEARN_IGNORE_DELTA = -0.03

# 反馈判定（§五）：接受 / 忽略 / 沉默（不调整权重，沉默也是信号）
OUTCOME_ACCEPT = "accepted"
OUTCOME_IGNORE = "ignored"
OUTCOME_NONE = "none"

# 学习产物表（ensure_nebula_schema 惰性幂等建表，见模块 docstring 建表口径）
WEIGHTS_TABLE = "nebula_dimension_weights"
PATTERNS_TABLE = "nebula_patterns"

# 维度对权重在 dict / 库表中的键分隔符（"dim_a|dim_b"）
_WEIGHT_KEY_SEP = "|"


def _weight_key(dim_a: str, dim_b: str) -> str:
    return f"{dim_a}{_WEIGHT_KEY_SEP}{dim_b}"


def ensure_nebula_schema(conn: sqlite3.Connection) -> None:
    """幂等建学习产物表（CREATE TABLE IF NOT EXISTS，可反复调用）。

    表结构即原 014_nebula.sql 的内容；因存量迁移测试硬编码版本列表，
    本轮不走 migrations/*.sql（见模块 docstring 建表口径）。
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {WEIGHTS_TABLE} (
            atom_id    TEXT NOT NULL,
            dim_a      TEXT NOT NULL,
            dim_b      TEXT NOT NULL,
            weight     REAL NOT NULL DEFAULT 0.5,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (atom_id, dim_a, dim_b)
        )
        """
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {PATTERNS_TABLE} (
            members_key    TEXT PRIMARY KEY,
            times_accepted INTEGER NOT NULL DEFAULT 0,
            times_ignored  INTEGER NOT NULL DEFAULT 0,
            last_outcome   TEXT,
            updated_at     TEXT NOT NULL
        )
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# 一、采集 —— 所有原子同时发声（DESIGN_NEBULA_ENGINE §三）
# ---------------------------------------------------------------------------


def atom_field(atom: Dict[str, Any]) -> Dict[str, Any]:
    """读取原子的场（DESIGN_RESONANCE_SPEC §二 的 {类别: {维度: 值}}）。

    持久化位置与 submit 镜像惯例一致：classification.gravity.field；
    同时宽容兼容 §二 的扁平写法 classification.field 与内存态顶层
    gravity.field / field。原子没有场时返回 {}（不参与共振）。
    """
    classification = atom.get("classification") or {}
    gravity = classification.get("gravity")
    if isinstance(gravity, dict) and isinstance(gravity.get("field"), dict):
        return gravity["field"]
    field = classification.get("field")
    if isinstance(field, dict):
        return field
    gravity_top = atom.get("gravity")
    if isinstance(gravity_top, dict) and isinstance(gravity_top.get("field"), dict):
        return gravity_top["field"]
    field_top = atom.get("field")
    return field_top if isinstance(field_top, dict) else {}


def atom_declared_weights(atom: Dict[str, Any]) -> Dict[str, float]:
    """读取原子在 meta 中声明的维度对权重（classification.gravity.weights）。

    键为 "dim_a|dim_b"；原子自带的先验权重（DESIGN_ATOM_GRAVITY §八：
    每个原子知道自己的哪些维度对哪些原子重要）。缺省 {}。
    """
    classification = atom.get("classification") or {}
    gravity = classification.get("gravity")
    declared = gravity.get("weights") if isinstance(gravity, dict) else None
    if not isinstance(declared, dict):
        return {}
    return {
        str(key): float(value)
        for key, value in declared.items()
        if isinstance(value, (int, float))
    }


def collect_fields(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    """采集所有原子的场（只读，复用 registry.core.list_atoms 查询惯例）。

    返回 {atom_id: field}；没有场的原子被跳过（它们此刻沉默）。
    """
    fields: Dict[str, Dict[str, Any]] = {}
    for atom in list_atoms(conn):
        field = atom_field(atom)
        if field:
            fields[atom["atom_id"]] = field
    return fields


def load_learned_weights(conn: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    """读取学习落库的维度对权重，{atom_id: {"a|b": weight}}。"""
    ensure_nebula_schema(conn)
    learned: Dict[str, Dict[str, float]] = {}
    rows = conn.execute(
        f"SELECT atom_id, dim_a, dim_b, weight FROM {WEIGHTS_TABLE}"
    ).fetchall()
    for atom_id, dim_a, dim_b, weight in rows:
        learned.setdefault(atom_id, {})[_weight_key(dim_a, dim_b)] = float(weight)
    return learned


def _merged_weights(
    conn: sqlite3.Connection, atoms: Iterable[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    """合并原子声明的先验权重与学习落库的权重（学习结果优先——更新更近）。"""
    merged: Dict[str, Dict[str, float]] = {}
    for atom in atoms:
        declared = atom_declared_weights(atom)
        if declared:
            merged[atom["atom_id"]] = dict(declared)
    for atom_id, learned in load_learned_weights(conn).items():
        merged.setdefault(atom_id, {}).update(learned)
    return merged


# ---------------------------------------------------------------------------
# 二、共振 —— 谁和谁在一起有意义（DESIGN_RESONANCE_SPEC §四）
# ---------------------------------------------------------------------------


def _weight_for(weights: Dict[Any, float], dim_a: str, dim_b: str) -> float:
    """取维度对权重：维度对无序，(na, nb) 与 (nb, na) 两个方向都查，
    兼容元组键与 "na|nb" 字符串键，缺省 0.5。"""
    for key in (
        (dim_a, dim_b),
        (dim_b, dim_a),
        _weight_key(dim_a, dim_b),
        _weight_key(dim_b, dim_a),
    ):
        if key in weights:
            return float(weights[key])
    return DEFAULT_WEIGHT


def compute_resonance(
    field_a: Dict[str, Any],
    field_b: Dict[str, Any],
    weights: Optional[Dict[Any, float]] = None,
) -> float:
    """共振公式（DESIGN_RESONANCE_SPEC §四，逐字实现）：

      total += w * weight * va * vb
      weight = 2.0（同类别）/ 0.5（跨类别），w = 维度对权重（缺省 0.5）
    """
    weights = weights or {}
    total = 0.0
    for cat_a, dims_a in field_a.items():
        if not isinstance(dims_a, dict):
            continue
        for cat_b, dims_b in field_b.items():
            if not isinstance(dims_b, dict):
                continue
            factor = SAME_CATEGORY_FACTOR if cat_a == cat_b else CROSS_CATEGORY_FACTOR
            for name_a, value_a in dims_a.items():
                if not isinstance(value_a, (int, float)):
                    continue
                for name_b, value_b in dims_b.items():
                    if not isinstance(value_b, (int, float)):
                        continue
                    w = _weight_for(weights, name_a, name_b)
                    total += w * factor * value_a * value_b
    return total


def resonance_map(
    atom_fields: Dict[str, Dict[str, Any]],
    weights_by_atom: Optional[Dict[str, Dict[Any, float]]] = None,
) -> List[Dict[str, Any]]:
    """全量两两共振（66 对的量级，§四 的 <1ms 口径）。

    原子对按 atom_id 排序取无向对 (a, b)；权重 a 侧优先、b 侧回落
    （§四 示例 w = a.weights.get(...)，双侧兼容见学习双方向记账）。
    返回按 (a, b) 字典序排序的边列表。
    """
    weights_by_atom = weights_by_atom or {}
    atom_ids = sorted(atom_fields)
    edges: List[Dict[str, Any]] = []
    for i, a in enumerate(atom_ids):
        for b in atom_ids[i + 1 :]:
            # 权重以 a 侧为先（§四 示例 w = a.weights.get(...)），
            # a 侧没有该键时回落 b 侧——每个原子自带维度权重（§八），
            # 学习对两个方向都记账，声明权重可能只写在一侧。
            pair_weights = dict(weights_by_atom.get(b) or {})
            pair_weights.update(weights_by_atom.get(a) or {})
            score = compute_resonance(atom_fields[a], atom_fields[b], pair_weights)
            edges.append({"a": a, "b": b, "score": score})
    return edges


# ---------------------------------------------------------------------------
# 三、聚类 —— 自然形成的临时组合（DESIGN_NEBULA_ENGINE §五）
# ---------------------------------------------------------------------------


def cluster_from_resonances(
    resonances: List[Dict[str, Any]], threshold: float = CLUSTER_THRESHOLD
) -> List[Dict[str, Any]]:
    """共振超过阈值的原子自然聚在一起。

    实现口径：超过阈值的边构成无向图，连通分量（并查集）即集群；
    集群强度 = 内部边的平均分。文档 §五 示例中的重叠集群（person 同时
    出现在三个集群）属软聚类语义，本轮取确定性硬聚类，后续可替换。
    返回按 (-strength, cluster_id) 排序，保证确定性。
    """
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> None:
        parent[find(x)] = find(y)

    strong_edges = [e for e in resonances if e["score"] >= threshold]
    for edge in strong_edges:
        union(edge["a"], edge["b"])

    groups: Dict[str, List[str]] = {}
    for edge in strong_edges:
        for atom_id in (edge["a"], edge["b"]):
            groups.setdefault(find(atom_id), [])
            if atom_id not in groups[find(atom_id)]:
                groups[find(atom_id)].append(atom_id)

    clusters: List[Dict[str, Any]] = []
    for members in groups.values():
        members = sorted(members)
        member_set = set(members)
        internal = [
            e
            for e in strong_edges
            if e["a"] in member_set and e["b"] in member_set
        ]
        strength = (
            sum(e["score"] for e in internal) / len(internal) if internal else 0.0
        )
        clusters.append(
            {
                "cluster_id": "cluster:" + "+".join(members),
                "members": members,
                "size": len(members),
                "strength": strength,
                "edges": internal,
            }
        )
    clusters.sort(key=lambda c: (-c["strength"], c["cluster_id"]))
    return clusters


# ---------------------------------------------------------------------------
# 五、学习 —— 不是训练，是痕迹（DESIGN_NEBULA_ENGINE §七 / §五 权重学习）
# ---------------------------------------------------------------------------


def _decay_factor(age_days: float) -> float:
    """时间衰减因子（§五）：最近 7 天 ×1.0，7-30 天 ×0.7，30+ 天 ×0.3。"""
    if age_days < 7:
        return 1.0
    if age_days < 30:
        return 0.7
    return 0.3


def _clamp_weight(value: float) -> float:
    return max(WEIGHT_MIN, min(WEIGHT_MAX, value))


def _participating_dim_pairs(
    members: List[str], fields: Dict[str, Dict[str, Any]]
) -> List[Tuple[str, str, str, str]]:
    """参与本轮共振的维度对：(a 侧 atom_id, b 侧 atom_id, dim_a, dim_b)。

    与共振计算同款口径：成员按 atom_id 排序取无向对 (a, b)，va*vb != 0
    的维度对即"参与"；同一对内的重复维度名去重。
    """
    seen = set()
    pairs: List[Tuple[str, str, str, str]] = []
    ordered = sorted(members)
    for i, a in enumerate(ordered):
        field_a = fields.get(a) or {}
        for b in ordered[i + 1 :]:
            field_b = fields.get(b) or {}
            for dims_a in field_a.values():
                if not isinstance(dims_a, dict):
                    continue
                for dims_b in field_b.values():
                    if not isinstance(dims_b, dict):
                        continue
                    for name_a, value_a in dims_a.items():
                        if not isinstance(value_a, (int, float)):
                            continue
                        for name_b, value_b in dims_b.items():
                            if not isinstance(value_b, (int, float)):
                                continue
                            if value_a * value_b == 0:
                                continue
                            key = (a, b, name_a, name_b)
                            if key not in seen:
                                seen.add(key)
                                pairs.append(key)
    return pairs


def _declared_lookup(
    weights: Dict[str, float], dim_a: str, dim_b: str
) -> Optional[float]:
    """声明权重查找（无序维度对，两个方向都试）；未声明返回 None。"""
    for key in (_weight_key(dim_a, dim_b), _weight_key(dim_b, dim_a)):
        if key in weights:
            return float(weights[key])
    return None


def _effective_weight(
    conn: sqlite3.Connection,
    declared: Dict[str, Dict[str, float]],
    a: str,
    b: str,
    dim_a: str,
    dim_b: str,
) -> Tuple[float, Optional[str]]:
    """取维度对当前有效权重与其时间戳（学习写入的口径来源）。

    优先级：学习落库（a 侧 → b 侧）→ 声明先验（a 侧 → b 侧）→ 缺省 0.5。
    返回 (weight, updated_at_or_None)。
    """
    for owner, da, db in ((a, dim_a, dim_b), (b, dim_b, dim_a)):
        row = conn.execute(
            f"SELECT weight, updated_at FROM {WEIGHTS_TABLE} "
            "WHERE atom_id = ? AND dim_a = ? AND dim_b = ?",
            (owner, da, db),
        ).fetchone()
        if row:
            return float(row[0]), row[1]
    for owner in (a, b):
        value = _declared_lookup(declared.get(owner) or {}, dim_a, dim_b)
        if value is not None:
            return value, None
    return DEFAULT_WEIGHT, None


def _record_pattern(
    conn: sqlite3.Connection, members: List[str], outcome: str, now: datetime
) -> Dict[str, Any]:
    """记录集群成员组合的痕迹（§七：有效模式 / 这次不适用）。"""
    members_key = "+".join(sorted(members))
    row = conn.execute(
        f"SELECT times_accepted, times_ignored FROM {PATTERNS_TABLE} "
        "WHERE members_key = ?",
        (members_key,),
    ).fetchone()
    accepted = (row[0] if row else 0) + (1 if outcome == OUTCOME_ACCEPT else 0)
    ignored = (row[1] if row else 0) + (1 if outcome == OUTCOME_IGNORE else 0)
    conn.execute(
        f"""
        INSERT INTO {PATTERNS_TABLE}
            (members_key, times_accepted, times_ignored, last_outcome, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(members_key) DO UPDATE SET
            times_accepted=excluded.times_accepted,
            times_ignored=excluded.times_ignored,
            last_outcome=excluded.last_outcome,
            updated_at=excluded.updated_at
        """,
        (members_key, accepted, ignored, outcome, now.isoformat()),
    )
    return {
        "members_key": members_key,
        "times_accepted": accepted,
        "times_ignored": ignored,
        "last_outcome": outcome,
    }


def learn_from_feedback(
    conn: sqlite3.Connection,
    members: List[str],
    outcome: str,
    fields: Optional[Dict[str, Dict[str, Any]]] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """按人的反馈更新参与维度的权重（§五 / §七）。

    - 接受 → 参与维度权重 +0.05 × 时间衰减因子，并记录"有效模式"；
    - 忽略 → 权重 -0.03 × 时间衰减因子，模式标记"这次不适用"；
    - 沉默（none 或其他）→ 不调整权重、不写模式（沉默也是信号）。
    权重范围 [0.1, 0.9]；无学习记录的维度对从原子声明的先验权重起调
    （classification.gravity.weights，§八），都没有时从缺省 0.5 起调；
    衰减按权重行的 updated_at 距今时长计算。返回 {updated, delta, pattern}。
    """
    if outcome not in (OUTCOME_ACCEPT, OUTCOME_IGNORE):
        return {"updated": 0, "delta": 0.0, "pattern": None}

    ensure_nebula_schema(conn)

    # 成员的声明先验权重（无学习记录时的起调基准）
    declared: Dict[str, Dict[str, float]] = {}
    wanted = set(members)
    for atom in list_atoms(conn):
        if atom.get("atom_id") in wanted:
            w = atom_declared_weights(atom)
            if w:
                declared[atom["atom_id"]] = w

    if fields is None:
        # 未显式给场时从注册中心补采（只读）
        fields = {
            atom_id: field
            for atom_id, field in collect_fields(conn).items()
            if atom_id in wanted
        }

    delta = LEARN_ACCEPT_DELTA if outcome == OUTCOME_ACCEPT else LEARN_IGNORE_DELTA
    now = now or datetime.now(timezone.utc)
    now_text = now.isoformat()
    updated = 0
    for a, b, dim_a, dim_b in _participating_dim_pairs(members, fields):
        base, base_updated_at = _effective_weight(conn, declared, a, b, dim_a, dim_b)
        factor = 1.0
        if base_updated_at is not None:
            try:
                age = now - datetime.fromisoformat(base_updated_at)
                factor = _decay_factor(age.total_seconds() / 86400.0)
            except (TypeError, ValueError):
                factor = 1.0  # 时间戳不可解析时按最新处理
        new_weight = _clamp_weight(base + delta * factor)
        # 两个方向同写一笔（每侧原子各记自己的权重，DESIGN_ATOM_GRAVITY §八），
        # 值保持一致——共振计算对无序对只认一个有效权重
        for owner, da, db in ((a, dim_a, dim_b), (b, dim_b, dim_a)):
            conn.execute(
                f"""
                INSERT INTO {WEIGHTS_TABLE} (atom_id, dim_a, dim_b, weight, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(atom_id, dim_a, dim_b) DO UPDATE SET
                    weight=excluded.weight,
                    updated_at=excluded.updated_at
                """,
                (owner, da, db, new_weight, now_text),
            )
            updated += 1
    conn.commit()
    pattern = _record_pattern(conn, members, outcome, now)
    conn.commit()
    return {"updated": updated, "delta": delta, "pattern": pattern}


# ---------------------------------------------------------------------------
# 主循环（DESIGN_NEBULA_ENGINE §一/§二/§八）
# ---------------------------------------------------------------------------


class NebulaEngine:
    """星云引擎主循环：可手动 step()，也可 start()/stop() 后台 daemon 线程。

    - interval 可注入（§二 的 30 秒节奏；测试用 0 或手动 step()，绝不真 sleep）；
    - threshold 可注入（§五 聚类阈值）；
    - conn_factory 可注入：文件库后台线程经它新开连接（notarize 线程惯例），
      缺省时自动从 PRAGMA database_list 推导；内存库退化为复用当前连接；
    - state 为 §八 状态机的简化版：idle / noticing / learning。
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        *,
        interval: float = LOOP_INTERVAL_SECONDS,
        threshold: float = CLUSTER_THRESHOLD,
        conn_factory: Optional[Callable[[], sqlite3.Connection]] = None,
    ) -> None:
        self._conn = conn
        self.interval = float(interval)
        self.threshold = float(threshold)
        self._conn_factory = conn_factory
        self.state = "idle"
        self._previous_clusters: set = set()
        self._pending_feedback: List[Tuple[List[str], str]] = []
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.last_step: Optional[Dict[str, Any]] = None

    # 一、采集（§三）
    def collect(self, conn: Optional[sqlite3.Connection] = None):
        c = conn or self._conn
        atoms = list_atoms(c)
        fields = {
            atom["atom_id"]: atom_field(atom)
            for atom in atoms
            if atom_field(atom)
        }
        return atoms, fields

    # 四、输出（§六：不是每次都要说话）+ 五、学习（§七：消费排队的反馈）
    def step(self, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """跑一次完整主循环（采集 → 共振 → 聚类 → 输出 → 学习）。"""
        c = conn or self._conn
        started = time.perf_counter()

        atoms, fields = self.collect(c)  # 1. 采集
        weights = _merged_weights(c, atoms)
        resonances = resonance_map(fields, weights)  # 2. 共振
        clusters = cluster_from_resonances(resonances, self.threshold)  # 3. 聚类

        # 4. 输出：集群和上一轮基本一样——没变化就不打扰（§六）；
        #    出现上一轮没有的集群 → 轻轻说。
        outputs = []
        current_keys = set()
        for cluster in clusters:
            current_keys.add(cluster["cluster_id"])
            if cluster["cluster_id"] not in self._previous_clusters:
                outputs.append(
                    {
                        "kind": "new_cluster",
                        "cluster_id": cluster["cluster_id"],
                        "members": cluster["members"],
                        "strength": cluster["strength"],
                    }
                )
        self._previous_clusters = current_keys

        # 5. 学习：消费本轮前排队的反馈（step 之外由 feedback() 排入）
        learned = {"updated": 0, "patterns": 0}
        pending, self._pending_feedback = self._pending_feedback, []
        for members, outcome in pending:
            result = learn_from_feedback(c, members, outcome, fields=fields)
            learned["updated"] += result["updated"]
            learned["patterns"] += 1 if result["pattern"] else 0
            self.state = "learning"

        if self.state != "learning":
            self.state = "noticing" if outputs else "idle"

        self.last_step = {
            "collected": len(fields),
            "pairs": len(resonances),
            "resonances": resonances,
            "clusters": clusters,
            "outputs": outputs,
            "learned": learned,
            "state": self.state,
            "elapsed_ms": (time.perf_counter() - started) * 1000.0,
        }
        return self.last_step

    def feedback(self, members: List[str], outcome: str) -> None:
        """排入一条人的反馈（接受/忽略/沉默），下一次 step 的学习阶段消费。"""
        self._pending_feedback.append((list(members), outcome))

    # ---- 后台线程（notarize 线程惯例）----

    def _resolve_conn_factory(self) -> Optional[Callable[[], sqlite3.Connection]]:
        if self._conn_factory is not None:
            return self._conn_factory
        db_path = ""
        try:
            for row in self._conn.execute("PRAGMA database_list").fetchall():
                if row[1] == "main":
                    db_path = row[2]
                    break
        except Exception:  # noqa: BLE001
            db_path = ""
        if not db_path:
            return None  # 内存库：退化为复用当前连接

        def _factory() -> sqlite3.Connection:
            c = sqlite3.connect(db_path)
            c.row_factory = sqlite3.Row
            return c

        return _factory

    def _loop(self) -> None:
        factory = self._resolve_conn_factory()
        while not self._stop.is_set():
            conn = None
            try:
                conn = factory() if factory else self._conn
                self.step(conn)
            except Exception:  # noqa: BLE001 - 引擎安静失败，绝不拖垮宿主
                pass
            finally:
                if conn is not None and conn is not self._conn:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001
                        pass
            # interval <= 0 时兜底 50ms，避免后台线程空转
            self._stop.wait(self.interval if self.interval > 0 else 0.05)

    def start(self) -> bool:
        """后台 daemon 线程跑主循环；已在运行返回 False。"""
        if self._thread is not None and self._thread.is_alive():
            return False
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="nebula-engine"
        )
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None


def run_nebula_step(
    conn: sqlite3.Connection, *, threshold: float = CLUSTER_THRESHOLD
) -> Dict[str, Any]:
    """一次性跑一轮主循环（无状态，模块级便捷入口，待 api.py 接线）。"""
    return NebulaEngine(conn, threshold=threshold).step()
