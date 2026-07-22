"""星云引擎主循环测试（nebula.py）。

规格来源：DESIGN_NEBULA_ENGINE.md（主循环五阶段 / 30 秒节奏 / 输出克制）、
DESIGN_ATOM_GRAVITY.md（总纲）、DESIGN_RESONANCE_SPEC.md（共振公式 / 权重学习）。

全部 hermetic：内存库 + migrations.migrate，不碰真实 registry.db、不访问网络、
绝不真 sleep（节奏做成可注入的 interval，测试只手动 step()）。
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone

import pytest
from migrations import migrate
from registry import REGISTRY_TABLE

import nebula
from nebula import (
    CLUSTER_THRESHOLD,
    CROSS_CATEGORY_FACTOR,
    DEFAULT_WEIGHT,
    LEARN_ACCEPT_DELTA,
    LEARN_IGNORE_DELTA,
    LOOP_INTERVAL_SECONDS,
    OUTCOME_ACCEPT,
    OUTCOME_IGNORE,
    OUTCOME_NONE,
    PATTERNS_TABLE,
    SAME_CATEGORY_FACTOR,
    WEIGHTS_TABLE,
    NebulaEngine,
    atom_field,
    cluster_from_resonances,
    compute_resonance,
    learn_from_feedback,
    resonance_map,
    run_nebula_step,
)


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    nebula.ensure_nebula_schema(c)  # 学习产物表为模块内惰性建表（见 nebula.py 建表口径）
    yield c
    c.close()


def _insert_atom(conn, atom_id, field=None, weights=None, status="registered"):
    """直接插注册表行（绕开 submit 流程，聚焦星云引擎本身）。"""
    classification = {"category": "sensor"}
    if field is not None or weights is not None:
        classification["gravity"] = {}
        if field is not None:
            classification["gravity"]["field"] = field
        if weights is not None:
            classification["gravity"]["weights"] = weights
    conn.execute(
        f"""
        INSERT INTO {REGISTRY_TABLE}
        (atom_id, name, version, description, purpose_json, architecture_json,
         ownership_json, classification_json, lifecycle_json, signature_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            atom_id,
            atom_id,
            "1.0.0",
            "",
            "{}",
            "{}",
            "{}",
            json.dumps(classification, ensure_ascii=False),
            json.dumps({"status": status}, ensure_ascii=False),
            f"sig-{atom_id}",
        ),
    )
    conn.commit()


def _weight_of(conn, atom_id, dim_a, dim_b):
    row = conn.execute(
        f"SELECT weight FROM {WEIGHTS_TABLE} "
        "WHERE atom_id = ? AND dim_a = ? AND dim_b = ?",
        (atom_id, dim_a, dim_b),
    ).fetchone()
    return None if row is None else row[0]


# ---------------------------------------------------------------------------
# 共振打分公式（DESIGN_RESONANCE_SPEC §四 的数值断言）
# ---------------------------------------------------------------------------


def test_resonance_same_category_factor():
    """同类别 ×2：total = w(0.5) × 2.0 × va × vb。"""
    a = {"物理": {"强度": 0.8}}
    b = {"物理": {"强度": 0.5}}
    assert compute_resonance(a, b) == pytest.approx(
        DEFAULT_WEIGHT * SAME_CATEGORY_FACTOR * 0.8 * 0.5
    )


def test_resonance_cross_category_factor():
    """跨类别 ×0.5：total = w(0.5) × 0.5 × va × vb。"""
    a = {"物理": {"强度": 0.8}}
    b = {"情绪": {"能量": 0.4}}
    assert compute_resonance(a, b) == pytest.approx(
        DEFAULT_WEIGHT * CROSS_CATEGORY_FACTOR * 0.8 * 0.4
    )


def test_resonance_custom_weight():
    """维度对权重参与乘积（缺省 0.5，指定后按指定值）。"""
    a = {"物理": {"强度": 0.8}}
    b = {"情绪": {"能量": 0.4}}
    assert compute_resonance(a, b, {("强度", "能量"): 0.9}) == pytest.approx(
        0.9 * CROSS_CATEGORY_FACTOR * 0.8 * 0.4
    )
    # 字符串键（库表/JSON 形态）同样生效
    assert compute_resonance(a, b, {"强度|能量": 0.9}) == pytest.approx(
        0.9 * CROSS_CATEGORY_FACTOR * 0.8 * 0.4
    )


def test_resonance_mixed_sum():
    """混合类别逐对求和（§四 公式 total += w·weight·va·vb 的完整形状）。"""
    a = {"物理": {"强度": 0.8, "密度": 0.9}, "情绪": {"能量": 0.3}}
    b = {"物理": {"密度": 0.5}, "情绪": {"能量": 0.4}}
    expected = (
        # a.物理 × b.物理（同类别 ×2）
        DEFAULT_WEIGHT * 2.0 * (0.8 * 0.5 + 0.9 * 0.5)
        # a.物理 × b.情绪（跨类别 ×0.5）
        + DEFAULT_WEIGHT * 0.5 * (0.8 * 0.4 + 0.9 * 0.4)
        # a.情绪 × b.物理（跨类别 ×0.5）
        + DEFAULT_WEIGHT * 0.5 * (0.3 * 0.5)
        # a.情绪 × b.情绪（同类别 ×2）
        + DEFAULT_WEIGHT * 2.0 * (0.3 * 0.4)
    )
    assert compute_resonance(a, b) == pytest.approx(expected)


def test_resonance_map_pairs_count():
    """12 个原子产生 66 对（§四 的 66 对口径），边按 (a, b) 排序。"""
    fields = {f"atom.{i:02d}": {"物理": {"强度": 0.5}} for i in range(12)}
    edges = resonance_map(fields)
    assert len(edges) == 66
    assert edges[0]["a"] == "atom.00" and edges[0]["b"] == "atom.01"
    assert all(e["a"] < e["b"] for e in edges)


def test_resonance_perf_caliber():
    """性能口径（§四：12 原子 × 5 维度 × 66 对 < 1ms）。

    纯 Python 双重循环应为毫秒级以下；这里给 500ms 的宽松上限防回归，
    避免 CI 抖动误伤。
    """
    fields = {
        f"atom.{i:02d}": {
            "物理": {"强度": 0.8, "密度": 0.9, "节奏": 0.6},
            "时间": {"持续": 2.0},
            "情绪": {"能量": 0.3, "开放度": 0.2},
            "状态": {"专注度": 0.7},
            "关系": {"协同": 0.5},
        }
        for i in range(12)
    }
    started = time.perf_counter()
    edges = resonance_map(fields)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert len(edges) == 66
    assert elapsed_ms < 500.0


# ---------------------------------------------------------------------------
# 聚类输出形状（DESIGN_NEBULA_ENGINE §五）
# ---------------------------------------------------------------------------


def test_cluster_shape_and_disjoint_groups():
    """超过阈值的边聚在一起；两簇互不连通 → 两个集群，形状完整。"""
    edges = [
        {"a": "a1", "b": "a2", "score": 1.0},
        {"a": "a2", "b": "a3", "score": 0.5},
        {"a": "b1", "b": "b2", "score": 0.8},
        {"a": "a1", "b": "b1", "score": 0.1},  # 低于阈值，不连
    ]
    clusters = cluster_from_resonances(edges, threshold=CLUSTER_THRESHOLD)
    assert len(clusters) == 2
    by_id = {c["cluster_id"]: c for c in clusters}
    ca = by_id["cluster:a1+a2+a3"]
    assert ca["members"] == ["a1", "a2", "a3"]
    assert ca["size"] == 3
    assert ca["strength"] == pytest.approx((1.0 + 0.5) / 2)  # 内部边平均分
    assert {e["a"] for e in ca["edges"]} == {"a1", "a2"}
    cb = by_id["cluster:b1+b2"]
    assert cb["members"] == ["b1", "b2"]
    assert cb["strength"] == pytest.approx(0.8)
    # 排序确定性：强度高的在前
    assert clusters[0]["cluster_id"] == "cluster:b1+b2"


def test_cluster_threshold_filters_weak_edges():
    edges = [{"a": "x", "b": "y", "score": CLUSTER_THRESHOLD - 1e-9}]
    assert cluster_from_resonances(edges) == []
    # 恰好等于阈值算超过（>=）
    edges = [{"a": "x", "b": "y", "score": CLUSTER_THRESHOLD}]
    assert len(cluster_from_resonances(edges)) == 1


# ---------------------------------------------------------------------------
# 主循环单步全阶段（DESIGN_NEBULA_ENGINE §一/§二/§六）
# ---------------------------------------------------------------------------


def test_step_full_cycle_all_phases(conn):
    """单步跑通五阶段：采集 → 共振 → 聚类 → 输出 → 学习。"""
    _insert_atom(conn, "a.weather", field={"物理": {"强度": 0.8}, "情绪": {"能量": 0.3}})
    _insert_atom(conn, "a.music", field={"物理": {"节奏": 0.5}, "情绪": {"能量": 0.4}})
    _insert_atom(conn, "a.person", field={"状态": {"专注度": 0.9}})

    engine = NebulaEngine(conn, interval=0)  # 节奏注入：手动步进，绝不真 sleep
    engine.feedback(["a.weather", "a.music"], OUTCOME_ACCEPT)
    result = engine.step()

    # 1. 采集：3 个有场的原子
    assert result["collected"] == 3
    # 2. 共振：3 对
    assert result["pairs"] == 3
    assert {tuple(sorted((e["a"], e["b"]))) for e in result["resonances"]} == {
        ("a.music", "a.person"),
        ("a.music", "a.weather"),
        ("a.person", "a.weather"),
    }
    # 3. 聚类：输出形状正确
    for cluster in result["clusters"]:
        assert set(cluster) == {"cluster_id", "members", "size", "strength", "edges"}
    # 4. 输出：第一轮所有集群都是新的（§六：新集群出现 → 轻轻说）
    assert [o["kind"] for o in result["outputs"]] == ["new_cluster"] * len(
        result["clusters"]
    )
    assert result["state"] == "learning"  # 本轮消费了一条反馈
    # 5. 学习：反馈被消费，权重落库
    assert result["learned"]["updated"] > 0
    assert result["learned"]["patterns"] == 1


def test_step_second_round_silent_when_unchanged(conn):
    """§六：集群和上一轮基本一样——没变化就不打扰。"""
    _insert_atom(conn, "a.x", field={"物理": {"强度": 0.9}})
    _insert_atom(conn, "a.y", field={"物理": {"强度": 0.9}})
    engine = NebulaEngine(conn, interval=0)
    first = engine.step()
    assert len(first["outputs"]) == 1  # 新集群出现
    second = engine.step()
    assert second["outputs"] == []  # 无变化 → 沉默
    assert second["state"] == "idle"


def test_loop_interval_constant_injectable():
    """§二：30 秒节奏是可注入的间隔常量。"""
    assert LOOP_INTERVAL_SECONDS == 30.0
    engine = NebulaEngine(None)  # 不 step，仅校验构造
    assert engine.interval == 30.0


# ---------------------------------------------------------------------------
# 边界：空库 / 单原子
# ---------------------------------------------------------------------------


def test_step_empty_registry(conn):
    result = run_nebula_step(conn)
    assert result["collected"] == 0
    assert result["pairs"] == 0
    assert result["clusters"] == []
    assert result["outputs"] == []
    assert result["learned"] == {"updated": 0, "patterns": 0}


def test_step_single_atom_no_pairs(conn):
    _insert_atom(conn, "a.lonely", field={"物理": {"强度": 1.0}})
    result = run_nebula_step(conn)
    assert result["collected"] == 1
    assert result["pairs"] == 0
    assert result["clusters"] == []


def test_atoms_without_field_are_silent(conn):
    """没有场的原子不参与共振（此刻沉默）。"""
    _insert_atom(conn, "a.nofield")
    _insert_atom(conn, "a.withfield", field={"物理": {"强度": 0.5}})
    result = run_nebula_step(conn)
    assert result["collected"] == 1
    assert result["pairs"] == 0


def test_atom_field_tolerant_locations():
    """场的读取位置：classification.gravity.field 优先，兼容扁平写法。"""
    assert atom_field({"classification": {"gravity": {"field": {"物理": {}}}}}) == {
        "物理": {}
    }
    assert atom_field({"classification": {"field": {"物理": {}}}}) == {"物理": {}}
    assert atom_field({"gravity": {"field": {"物理": {}}}}) == {"物理": {}}
    assert atom_field({"field": {"物理": {}}}) == {"物理": {}}
    assert atom_field({"classification": {}}) == {}


# ---------------------------------------------------------------------------
# 学习阶段（DESIGN_RESONANCE_SPEC §五 / DESIGN_NEBULA_ENGINE §七）
# ---------------------------------------------------------------------------


def test_learn_accept_increases_weights(conn):
    """接受 → 参与维度权重 +0.05（从缺省 0.5 起调到 0.55），方向正确。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    result = learn_from_feedback(
        conn, ["a.weather", "a.music"], OUTCOME_ACCEPT, fields=fields
    )
    assert result["updated"] == 2  # 两个方向各记一笔
    assert result["delta"] == LEARN_ACCEPT_DELTA
    assert _weight_of(conn, "a.weather", "强度", "节奏") == pytest.approx(0.55)
    assert _weight_of(conn, "a.music", "节奏", "强度") == pytest.approx(0.55)


def test_learn_ignore_decreases_weights(conn):
    """忽略 → 参与维度权重 -0.03（0.5 → 0.47），方向正确。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    result = learn_from_feedback(
        conn, ["a.weather", "a.music"], OUTCOME_IGNORE, fields=fields
    )
    assert result["delta"] == LEARN_IGNORE_DELTA
    assert _weight_of(conn, "a.weather", "强度", "节奏") == pytest.approx(0.47)


def test_learn_none_is_silent(conn):
    """沉默 → 不调整权重、不写模式（沉默也是信号，§七）。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    result = learn_from_feedback(
        conn, ["a.weather", "a.music"], OUTCOME_NONE, fields=fields
    )
    assert result == {"updated": 0, "delta": 0.0, "pattern": None}
    assert conn.execute(f"SELECT COUNT(*) FROM {WEIGHTS_TABLE}").fetchone()[0] == 0
    assert conn.execute(f"SELECT COUNT(*) FROM {PATTERNS_TABLE}").fetchone()[0] == 0


def test_learn_weight_clamped(conn):
    """权重范围 [0.1, 0.9]（§五）：越界被夹住。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    now = datetime.now(timezone.utc)
    # 先放到 0.89，接受一次应夹到 0.9
    conn.execute(
        f"INSERT INTO {WEIGHTS_TABLE} (atom_id, dim_a, dim_b, weight, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("a.weather", "强度", "节奏", 0.89, now.isoformat()),
    )
    conn.commit()
    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_ACCEPT, fields=fields)
    assert _weight_of(conn, "a.weather", "强度", "节奏") == pytest.approx(0.9)
    # 再把两个方向都放到 0.11（学习对两个方向同写一笔，需同步构造），
    # 忽略一次应夹到 0.1
    for owner, da, db in (("a.weather", "强度", "节奏"), ("a.music", "节奏", "强度")):
        conn.execute(
            f"UPDATE {WEIGHTS_TABLE} SET weight = 0.11, updated_at = ? "
            "WHERE atom_id = ? AND dim_a = ? AND dim_b = ?",
            (now.isoformat(), owner, da, db),
        )
    conn.commit()
    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_IGNORE, fields=fields)
    assert _weight_of(conn, "a.weather", "强度", "节奏") == pytest.approx(0.1)


def test_learn_time_decay(conn):
    """时间衰减（§五）：30+ 天的旧权重调整幅度 ×0.3（+0.05 → +0.015）。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    conn.execute(
        f"INSERT INTO {WEIGHTS_TABLE} (atom_id, dim_a, dim_b, weight, updated_at) "
        "VALUES (?, ?, ?, ?, ?)",
        ("a.weather", "强度", "节奏", 0.5, old),
    )
    conn.commit()
    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_ACCEPT, fields=fields)
    assert _weight_of(conn, "a.weather", "强度", "节奏") == pytest.approx(
        0.5 + 0.05 * 0.3
    )


def test_learn_records_pattern(conn):
    """§七：接受记"有效模式"，忽略记"这次不适用"，计数累加。"""
    fields = {
        "a.weather": {"物理": {"强度": 0.8}},
        "a.music": {"物理": {"节奏": 0.5}},
    }
    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_ACCEPT, fields=fields)
    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_IGNORE, fields=fields)
    row = conn.execute(
        f"SELECT times_accepted, times_ignored, last_outcome FROM {PATTERNS_TABLE} "
        "WHERE members_key = ?",
        ("a.music+a.weather",),
    ).fetchone()
    assert tuple(row) == (1, 1, "ignored")


def test_learned_weights_feed_back_into_resonance(conn):
    """学习闭环：落库权重参与下一轮共振计算（引擎可见）。"""
    _insert_atom(conn, "a.weather", field={"物理": {"强度": 0.8}})
    _insert_atom(conn, "a.music", field={"情绪": {"能量": 0.4}})
    before = run_nebula_step(conn)["resonances"][0]["score"]
    assert before == pytest.approx(0.5 * 0.5 * 0.8 * 0.4)  # 缺省权重

    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_ACCEPT)
    after = run_nebula_step(conn)["resonances"][0]["score"]
    # 权重 0.55 后：0.55 × 0.5 × 0.8 × 0.4
    assert after == pytest.approx(0.55 * 0.5 * 0.8 * 0.4)
    assert after > before


def test_declared_weights_used_until_learned(conn):
    """原子 meta 声明的先验权重生效；学习落库后优先（学习更近）。"""
    _insert_atom(
        conn,
        "a.weather",
        field={"物理": {"强度": 0.8}},
        weights={"强度|能量": 0.9},
    )
    _insert_atom(conn, "a.music", field={"情绪": {"能量": 0.4}})
    score = run_nebula_step(conn)["resonances"][0]["score"]
    assert score == pytest.approx(0.9 * 0.5 * 0.8 * 0.4)

    learn_from_feedback(conn, ["a.weather", "a.music"], OUTCOME_IGNORE)
    score2 = run_nebula_step(conn)["resonances"][0]["score"]
    # 0.9 - 0.03 = 0.87（学习结果覆盖声明值）
    assert score2 == pytest.approx(0.87 * 0.5 * 0.8 * 0.4)
