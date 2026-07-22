"""星云引擎 × 安全网 × api.py 接线集成测试（跨代理契约）。

契约来源（钉死）：
1. 单例访问器 safety_net.get_safety_net() / nebula.get_nebula_engine(conn=None)
   （线程安全、可重置用于测试，对齐 get_chain/get_provider 惯例——测试内以
   monkeypatch 重置模块级私有单例，同 test_notarize_api 重置 _chain 的手法）。
2. NebulaEngine(conn, ..., safety_net=None)：注入后 step() 每循环报心跳/巡检；
   安全模式激活时退化为轻量空转（仍报心跳，跳过共振/聚类/输出/学习，
   返回 dict 含 "safe_mode": True）；safety_net=None 时与旧版完全一致。
3. engine.abort_node(node_id) -> bool：安全网卡死恢复的回调接缝；
   engine 无此函数时回调缺失即 no-op。
4. api.py 五端点：GET /safety-net/status、GET /safety-net/events?limit=50、
   POST /safety-net/exit（admin，{"reset": bool=false}）、GET /nebula/status、
   POST /nebula/step（admin）。

接线由并行代理实现；未合入的接口按仓库惯例跳过（importorskip 同款语义，
见 test_notarize_api.py），跳过原因逐条写明「等待实现：」与期望接口，
实现合入后复跑自动转活。

全部 hermetic：内存库/tmp_path + FakeClock 注入单调时钟，不碰真实
registry.db、不访问网络、不真 sleep、不真起线程（只手动 step）。
"""

from __future__ import annotations

import inspect
import json
import sqlite3

import pytest
from migrations import migrate
from registry import REGISTRY_TABLE

import nebula
import safety_net
import engine as workflow_engine
from nebula import WEIGHTS_TABLE, NebulaEngine
from safety_net import (
    ANOMALY_HEARTBEAT_TIMEOUT,
    ANOMALY_SILENCE,
    ANOMALY_STUCK_NODE,
    MODE_SAFE,
    SafetyNet,
)


# ---------------------------------------------------------------------------
# 「等待实现」守卫：接口未合入时跳过并写明期望接口（合入后自动转活）
# ---------------------------------------------------------------------------


def _require(condition: bool, expectation: str) -> None:
    if not condition:
        pytest.skip(f"等待实现：{expectation}")


def _nebula_accepts_safety_net() -> bool:
    return "safety_net" in inspect.signature(NebulaEngine.__init__).parameters


def _require_nebula_wiring() -> None:
    _require(
        _nebula_accepts_safety_net(),
        "NebulaEngine.__init__(conn, *, ..., safety_net=None)；注入后 step() "
        "每循环调 SafetyNet 的心跳/巡检，安全模式返回 dict 含 \"safe_mode\": True",
    )


def _require_singletons() -> None:
    _require(
        hasattr(safety_net, "get_safety_net"),
        "safety_net.get_safety_net() -> SafetyNet 单例访问器（可重置用于测试）",
    )
    _require(
        hasattr(nebula, "get_nebula_engine"),
        "nebula.get_nebula_engine(conn=None) -> NebulaEngine 单例访问器"
        "（默认注入 get_safety_net()，可重置用于测试）",
    )


def _reset_singletons(monkeypatch) -> None:
    """重置两个模块级单例（get_chain 惯例：monkeypatch 私有全局为 None）。

    优先调实现方可能提供的 reset_* 函数；否则按 _safety_net / _nebula_engine
    命名惯例 monkeypatch。teardown 时 monkeypatch 自动还原，单例不跨用例泄漏。
    """
    for mod, reset_name, global_name in (
        (safety_net, "reset_safety_net", "_safety_net"),
        (nebula, "reset_nebula_engine", "_nebula_engine"),
    ):
        reset_fn = getattr(mod, reset_name, None)
        if callable(reset_fn):
            reset_fn()
        elif hasattr(mod, global_name):
            monkeypatch.setattr(mod, global_name, None)


# ---------------------------------------------------------------------------
# 公共 fixture 与桩（对齐 test_nebula.py / test_safety_net.py 惯例）
# ---------------------------------------------------------------------------


class FakeClock:
    """单调时钟桩：advance() 推进时间（对齐 test_safety_net.py）。"""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture()
def clock():
    return FakeClock()


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    migrate(c)
    nebula.ensure_nebula_schema(c)
    yield c
    c.close()


def _insert_atom(conn, atom_id, field=None, status="registered"):
    """直接插注册表行（同 test_nebula.py，绕开 submit 流程）。"""
    classification = {"category": "sensor"}
    if field is not None:
        classification["gravity"] = {"field": field}
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


def _insert_resonating_pair(conn):
    """两个场相同的原子：共振分 0.5×2.0×0.81=0.81 ≥ 阈值，必成集群。"""
    _insert_atom(conn, "a.x", field={"物理": {"强度": 0.9}})
    _insert_atom(conn, "a.y", field={"物理": {"强度": 0.9}})


def _drive_into_safe_mode(net):
    """制造 3 种异常进入安全模式（同 test_safety_net.py 的手法）。"""
    net.save_snapshot(["a", "b"], {})
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)
    return net.inspect_loop(
        had_output=False, cluster_members=["x", "y"], weights={"w": 0.99}
    )


def _event_kinds(net, event_type):
    return {e["kind"] for e in net.events() if e["event_type"] == event_type}


# ---------------------------------------------------------------------------
# (1) 注入 safety_net 后 step() 驱动心跳/巡检
# ---------------------------------------------------------------------------


def test_step_reports_heartbeat_and_enables_timeout_detection(conn, clock):
    """step() 每循环报心跳：巡检可见心跳时刻；停步超时由 check() 兜底发现。"""
    _require_nebula_wiring()
    net = SafetyNet(now=clock)
    engine = NebulaEngine(conn, interval=0, safety_net=net)
    _insert_resonating_pair(conn)

    result = engine.step()
    assert result["outputs"]  # 新集群出现（§六）
    status = net.status()
    assert status["last_heartbeat_age_seconds"] == 0.0  # 心跳已到达安全网
    assert status["consecutive_silent_loops"] == 0  # 有输出不计沉默

    # 引擎不再 step（主循环卡住）：假时钟推进过 30s 阈值 → check() 报心跳超时
    clock.advance(safety_net.HEARTBEAT_TIMEOUT_SECONDS + 1)
    report = net.check()
    assert ANOMALY_HEARTBEAT_TIMEOUT in {a.kind for a in report.anomalies}


def test_silent_steps_drive_silence_fallback_counting(conn, clock):
    """连续无输出的 step 触发沉默兜底计数（阈值 3 次循环）。"""
    _require_nebula_wiring()
    net = SafetyNet(now=clock)
    engine = NebulaEngine(conn, interval=0, safety_net=net)
    _insert_resonating_pair(conn)

    first = engine.step()
    assert first["outputs"]  # 第 1 轮有新集群输出
    for _ in range(2):  # 第 2、3 轮集群无变化 → 沉默，未达阈值
        engine.step()
    assert net.status()["consecutive_silent_loops"] == 2
    assert ANOMALY_SILENCE not in _event_kinds(net, "anomaly")

    engine.step()  # 第 4 轮 = 连续第 3 次沉默 → 触发沉默兜底（第二节第 2 条）
    assert net.status()["consecutive_silent_loops"] == 3
    assert ANOMALY_SILENCE in _event_kinds(net, "anomaly")
    assert "fallback_suggestion" in _event_kinds(net, "action")


# ---------------------------------------------------------------------------
# (2) 安全模式：step() 退化为轻量空转；退出后恢复
# ---------------------------------------------------------------------------


def test_safe_mode_step_degrades_to_lightweight_idle(conn, clock):
    """安全模式：不共振/不聚类/不输出/不学习，返回 safe_mode: True，心跳仍到。"""
    _require_nebula_wiring()
    net = SafetyNet(now=clock)
    _drive_into_safe_mode(net)
    assert net.in_safe_mode()

    engine = NebulaEngine(conn, interval=0, safety_net=net)
    _insert_resonating_pair(conn)
    engine.feedback(["a.x", "a.y"], "accepted")  # 排队学习，验证安全模式不消费

    clock.advance(5)
    result = engine.step()
    assert result["safe_mode"] is True
    assert result.get("outputs", []) == []
    assert result.get("clusters", []) == []
    # 不写学习记录（不学习：权重表零写入）
    assert conn.execute(f"SELECT COUNT(*) FROM {WEIGHTS_TABLE}").fetchone()[0] == 0
    # 轻量空转仍报心跳（保引擎不崩溃是安全网自身定位）
    assert net.status()["last_heartbeat_age_seconds"] == 0.0


def test_exit_safe_mode_resumes_normal_output(conn, clock):
    """退出安全模式后下一轮 step 恢复完整五阶段。"""
    _require_nebula_wiring()
    net = SafetyNet(now=clock)
    _drive_into_safe_mode(net)
    engine = NebulaEngine(conn, interval=0, safety_net=net)
    _insert_resonating_pair(conn)
    assert engine.step()["safe_mode"] is True

    net.exit_safe_mode()
    result = engine.step()
    assert result.get("safe_mode") is not True
    assert result["clusters"]  # 共振/聚类恢复
    assert result["outputs"]  # 新集群重新输出（§六）
    assert result["collected"] == 2


# ---------------------------------------------------------------------------
# (3) safety_net=None：回归锚（行为与旧版完全一致）
# ---------------------------------------------------------------------------


def test_no_safety_net_matches_legacy_behavior(conn):
    """safety_net=None 时结果键与旧版一致，无 safe_mode 键，输出克制不变。"""
    _require_nebula_wiring()
    _insert_resonating_pair(conn)
    legacy_keys = {
        "collected",
        "pairs",
        "resonances",
        "clusters",
        "outputs",
        "learned",
        "state",
        "elapsed_ms",
    }
    for engine in (
        NebulaEngine(conn, interval=0),  # 缺省
        NebulaEngine(conn, interval=0, safety_net=None),  # 显式 None
    ):
        first = engine.step()
        assert legacy_keys <= set(first)
        assert "safe_mode" not in first  # 旧版无此键
        assert len(first["outputs"]) == 1  # 新集群出现
        assert engine.step()["outputs"] == []  # 无变化不打扰（§六）


# ---------------------------------------------------------------------------
# (4) abort_node 接缝：卡死恢复 → engine.abort_node；缺失即 no-op
# ---------------------------------------------------------------------------


def test_engine_abort_node_unknown_node_returns_false():
    """engine.abort_node(node_id) -> bool：不存在/已结束返回 False，异常不抛出。"""
    abort_node = getattr(workflow_engine, "abort_node", None)
    _require(
        callable(abort_node),
        "engine.abort_node(node_id: str) -> bool（中止在飞节点 True，"
        "不存在/已结束 False，异常不抛出）",
    )
    assert abort_node("wf.node.不存在") is False


def test_stuck_node_recovery_goes_through_engine_seam(clock):
    """在飞节点超时 → 安全网卡死恢复经 engine.abort_node 接缝，节点标记 skipped。"""
    abort_node = getattr(workflow_engine, "abort_node", None)
    _require(callable(abort_node), "engine.abort_node(node_id: str) -> bool")
    # 按契约第 3 条的接线方式构造：惰性 import engine 取回调注入安全网
    net = SafetyNet(now=clock, abort_node=abort_node)
    net.node_started("wf.node.1")
    clock.advance(safety_net.STUCK_NODE_TIMEOUT_SECONDS + 1)

    report = net.check()
    assert ANOMALY_STUCK_NODE in {a.kind for a in report.anomalies}
    action = next(a for a in report.actions if a.type == "abort_node")
    assert action.payload["node_id"] == "wf.node.1"
    assert action.payload["skipped"] is True
    # 引擎侧无此在飞节点 → 回调返回 False，但安全网不崩、节点仍 skipped
    assert action.payload["abort_callback_ok"] is False
    assert "wf.node.1" in net.aborted_nodes()
    assert "wf.node.1" not in net.status()["nodes_in_flight"]


def test_missing_abort_node_callback_is_noop(clock):
    """engine 无 abort_node 时（回调缺失）卡死恢复仍走通：no-op 不崩。"""
    net = SafetyNet(now=clock, abort_node=getattr(object(), "abort_node", None))
    net.node_started("wf.node.1")
    clock.advance(safety_net.STUCK_NODE_TIMEOUT_SECONDS + 1)
    report = net.check()  # 不抛异常
    action = next(a for a in report.actions if a.type == "abort_node")
    assert action.payload["skipped"] is True
    assert action.payload["abort_callback_ok"] is None  # 无回调可调
    assert "wf.node.1" in net.aborted_nodes()


# ---------------------------------------------------------------------------
# (6) 单例访问器：同一实例、可重置、默认注入
# ---------------------------------------------------------------------------


def test_singletons_identity_and_reset(conn, monkeypatch):
    """重复获取同一实例；重置后为新实例（get_chain 测试惯例）。"""
    _require_singletons()
    _reset_singletons(monkeypatch)
    net_a = safety_net.get_safety_net()
    assert safety_net.get_safety_net() is net_a
    engine_a = nebula.get_nebula_engine(conn)
    assert nebula.get_nebula_engine() is engine_a
    assert nebula.get_nebula_engine(conn) is engine_a

    _reset_singletons(monkeypatch)
    _require(
        safety_net.get_safety_net() is not net_a,
        "单例可重置用于测试：safety_net._safety_net 模块级私有全局"
        "（或 reset_safety_net()），对齐 get_chain/_chain 惯例",
    )
    _require(
        nebula.get_nebula_engine(conn) is not engine_a,
        "单例可重置用于测试：nebula._nebula_engine 模块级私有全局"
        "（或 reset_nebula_engine()），对齐 get_chain/_chain 惯例",
    )


def test_get_nebula_engine_injects_safety_net_singleton(conn, monkeypatch):
    """get_nebula_engine 默认注入 get_safety_net()：单例安全网进安全模式，
    引擎 step 立即退化（行为断言，不依赖私有属性名）。"""
    _require_singletons()
    _require_nebula_wiring()
    _reset_singletons(monkeypatch)
    net = safety_net.get_safety_net()
    _drive_into_safe_mode(net)

    engine = nebula.get_nebula_engine(conn)
    _insert_resonating_pair(conn)
    result = engine.step()
    assert result.get("safe_mode") is True  # 引擎看见了单例安全网的安全模式


def test_safety_net_singleton_has_abort_seam_injected(monkeypatch):
    """接线方为单例安全网注入 abort_node 回调（惰性 import engine 兜底）。"""
    _require_singletons()
    _reset_singletons(monkeypatch)
    net = safety_net.get_safety_net()
    _require(
        getattr(net, "_abort_node", None) is not None,
        "get_safety_net() 构造时用惰性 import engine + try/except 注入 "
        "abort_node 回调；engine 无此函数时回退 None（no-op）",
    )


# ---------------------------------------------------------------------------
# (5) api.py 五端点（viewer/admin 权限惯例同 notarize 端点）
# ---------------------------------------------------------------------------

from api import create_app  # noqa: E402
from auth import create_token  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ADMIN_TOKEN = "admin-secret"
VIEWER_TOKEN = "viewer-secret"


def _h(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """TestClient + admin/viewer 双令牌（对齐 test_notarize_api.py 惯例）。"""
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    _reset_singletons(monkeypatch)  # 端点走单例访问器，逐用例重置防泄漏
    db = tmp_path / "wiring-api.db"
    setup_conn = sqlite3.connect(str(db))
    migrate(setup_conn)
    create_token(setup_conn, ADMIN_TOKEN, role="admin")
    create_token(setup_conn, VIEWER_TOKEN, role="viewer")
    setup_conn.close()
    with TestClient(create_app(db)) as c:
        yield c


def _require_api_wiring(client, *paths):
    _require_singletons()
    routes = {getattr(r, "path", None) for r in client.app.routes}
    missing = [p for p in paths if p not in routes]
    _require(
        not missing,
        "api.py 端点未接线："
        + ", ".join(missing)
        + "（走 get_safety_net()/get_nebula_engine() 单例 + 惰性导入惯例）",
    )


def test_api_safety_net_status_and_events(client):
    """GET /safety-net/status 原样字典；GET /safety-net/events?limit= 生效。"""
    _require_api_wiring(client, "/safety-net/status", "/safety-net/events")

    r = client.get("/safety-net/status", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "normal"
    for key in ("consecutive_silent_loops", "nodes_in_flight", "snapshot_count"):
        assert key in body  # safety_net.status() 原样字典
    assert client.get("/safety-net/status").status_code == 401  # 无凭证

    # 制造事件：连续 3 次沉默巡检 → anomaly + action + notification
    net = safety_net.get_safety_net()
    for _ in range(3):
        net.inspect_loop(had_output=False)
    r = client.get("/safety-net/events", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    events = r.json()["events"]
    assert len(events) >= 3
    assert client.get(
        "/safety-net/events", params={"limit": 1}, headers=_h(VIEWER_TOKEN)
    ).json()["events"] == events[:1]  # limit 生效（最新在前）


def test_api_safety_net_exit_reset_two_modes(client):
    """POST /safety-net/exit：admin 专属；reset 两态；未在安全模式 exited False。"""
    _require_api_wiring(client, "/safety-net/exit", "/safety-net/status")

    assert client.post("/safety-net/exit", json={}).status_code == 401
    assert (
        client.post("/safety-net/exit", json={}, headers=_h(VIEWER_TOKEN)).status_code
        == 403
    )

    # 未在安全模式：exited False
    r = client.post("/safety-net/exit", json={}, headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200, r.text
    assert r.json()["exited"] is False

    net = safety_net.get_safety_net()
    _drive_into_safe_mode(net)
    assert net.in_safe_mode()
    r = client.post("/safety-net/exit", json={"reset": False}, headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200, r.text
    assert r.json() == {"exited": True, "reset": False, "mode": "normal"}
    assert not net.in_safe_mode()

    # reset=True：完全重置（清空快照与学习计数）
    _drive_into_safe_mode(net)
    r = client.post("/safety-net/exit", json={"reset": True}, headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200, r.text
    assert r.json()["exited"] is True and r.json()["reset"] is True
    status = client.get("/safety-net/status", headers=_h(VIEWER_TOKEN)).json()
    assert status["snapshot_count"] == 0
    assert status["consecutive_silent_loops"] == 0


def test_api_nebula_status_and_manual_step(client):
    """GET /nebula/status 形状；POST /nebula/step（admin）驱动 loop_count+1。"""
    _require_api_wiring(client, "/nebula/status", "/nebula/step")

    r = client.get("/nebula/status", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["loop_count"], int)
    assert body["safe_mode"] is False
    assert isinstance(body["clusters"], list)
    assert client.get("/nebula/status").status_code == 401

    assert client.post("/nebula/step").status_code == 401
    assert client.post("/nebula/step", headers=_h(VIEWER_TOKEN)).status_code == 403

    r = client.post("/nebula/step", headers=_h(ADMIN_TOKEN))
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), dict)  # 手动单步结果 dict
    loop_count = client.get("/nebula/status", headers=_h(VIEWER_TOKEN)).json()[
        "loop_count"
    ]
    assert loop_count == body["loop_count"] + 1

    client.post("/nebula/step", headers=_h(ADMIN_TOKEN))
    assert client.get("/nebula/status", headers=_h(VIEWER_TOKEN)).json()[
        "loop_count"
    ] == loop_count + 1
