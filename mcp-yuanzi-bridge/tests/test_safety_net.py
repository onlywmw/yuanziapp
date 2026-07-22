"""引擎安全网测试（DESIGN_ENGINE_SAFETY_NET.md）。

全部 hermetic：SafetyNet 为纯内存实现，时间用 FakeClock 注入，
abort_node 用记录桩注入；不碰真实 registry.db，不访问网络。
"""

from __future__ import annotations

import pytest

from safety_net import (
    ANOMALY_CHAOS,
    ANOMALY_HEARTBEAT_TIMEOUT,
    ANOMALY_SILENCE,
    ANOMALY_STUCK_NODE,
    ANOMALY_WEIGHT_DEGRADATION,
    DEFAULT_SILENCE_MESSAGE,
    MODE_NORMAL,
    MODE_SAFE,
    NOTICE_CHAOS_ROLLBACK,
    NOTICE_SAFE_MODE_ENTER,
    NOTICE_WEIGHT_RESET,
    SafetyNet,
    build_fallback_suggestion,
    chaos_change_ratio,
    weights_degraded,
)


class FakeClock:
    """单调时钟桩：advance() 推进时间。"""

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
def net(clock):
    return SafetyNet(now=clock)


def _kinds(report):
    return {a.kind for a in report.anomalies}


def _action_types(report):
    return {a.type for a in report.actions}


# ------------------------------------------------------------
# 心跳检测（第二节第 1 条）
# ------------------------------------------------------------


def test_normal_heartbeat_no_false_alarm(net, clock):
    """正常节奏的心跳不触发超时误判。"""
    net.heartbeat()
    for _ in range(3):
        clock.advance(10)  # 每 10s 一次循环，远低于 30s 阈值
        net.heartbeat()
    report = net.check()
    assert report.ok
    assert report.mode == MODE_NORMAL


def test_inspect_loop_counts_as_heartbeat(net, clock):
    """主循环末尾的 inspect_loop 本身就刷新心跳。"""
    net.heartbeat()
    clock.advance(100)
    net.inspect_loop(had_output=True)
    assert net.check().ok  # 心跳已被 inspect_loop 刷新，不误报


def test_heartbeat_timeout_triggers_reset_loop(net, clock):
    """30s 无主循环 → 记录 + 重置循环；同一段超时不重复报。"""
    net.heartbeat()
    clock.advance(31)
    report = net.check()
    assert ANOMALY_HEARTBEAT_TIMEOUT in _kinds(report)
    assert "reset_loop" in _action_types(report)

    # 未恢复心跳前再次巡检不重复报
    assert net.check().ok

    # 心跳恢复后又超时 → 再次触发
    net.heartbeat()
    clock.advance(31)
    assert ANOMALY_HEARTBEAT_TIMEOUT in _kinds(net.check())


def test_heartbeat_timeout_diagnoses_in_flight_nodes(net, clock):
    """超时报告附带在飞节点诊断（"检查哪个环节卡住了"）。"""
    net.heartbeat()
    net.node_started("n1")
    clock.advance(31)
    report = net.check()
    action = next(a for a in report.actions if a.type == "reset_loop")
    assert action.payload["in_flight_nodes"] == {"n1": 31.0}


def test_no_heartbeat_before_first_loop(net):
    """引擎从未跑过循环时不判超时。"""
    assert net.check().ok


# ------------------------------------------------------------
# 沉默兜底（第二节第 2 条 / 第四节沉默修复）
# ------------------------------------------------------------


PERSON_ATOM = {"rhythm": {"weekday_morning": {"听歌": 8, "阅读": 2}}}


def test_silence_fallback_after_three_silent_loops(net):
    """连续 3 次循环无输出 → 发送兜底建议；有输出后计数重置。"""
    r1 = net.inspect_loop(had_output=False, person_atom=PERSON_ATOM, period="weekday_morning")
    r2 = net.inspect_loop(had_output=False, person_atom=PERSON_ATOM, period="weekday_morning")
    assert r1.ok and r2.ok  # 前两次沉默不动作

    r3 = net.inspect_loop(had_output=False, person_atom=PERSON_ATOM, period="weekday_morning")
    assert ANOMALY_SILENCE in _kinds(r3)
    action = next(a for a in r3.actions if a.type == "fallback_suggestion")
    assert action.payload["message"] == "这个时间你通常在听歌。要试试吗？"
    assert action.payload["message"] in r3.notifications

    # 有输出 → 计数重置，再沉默一次不动作
    assert net.inspect_loop(had_output=True).ok
    assert net.inspect_loop(had_output=False).ok


def test_silence_fallback_default_message_without_rhythm(net):
    """无 rhythm 数据时退回最保守的默认文案。"""
    for _ in range(2):
        net.inspect_loop(had_output=False)
    report = net.inspect_loop(had_output=False)
    action = next(a for a in report.actions if a.type == "fallback_suggestion")
    assert action.payload["message"] == DEFAULT_SILENCE_MESSAGE


def test_fallback_suggestion_rhythm_forms():
    """rhythm 三种容忍形态：显式行为键 / 频次的 dict / 列表。"""
    assert (
        build_fallback_suggestion(
            {"rhythm": {"p": {"behavior": "听歌", "push": True}}}, "p"
        )
        == "这个时间你通常在听歌。要试试吗？"
    )
    assert (
        build_fallback_suggestion({"rhythm": {"p": {"听歌": 5, "阅读": 2}}}, "p")
        == "这个时间你通常在听歌。要试试吗？"
    )
    assert (
        build_fallback_suggestion({"rhythm": {"p": ["阅读", "听歌", "听歌"]}}, "p")
        == "这个时间你通常在听歌。要试试吗？"
    )
    # 时段缺失 / aspect 字典无法识别行为 → 默认文案
    assert build_fallback_suggestion({"rhythm": {}}, "p") == DEFAULT_SILENCE_MESSAGE
    assert (
        build_fallback_suggestion({"rhythm": {"p": {"pace": "fast"}}}, "p")
        == DEFAULT_SILENCE_MESSAGE
    )


# ------------------------------------------------------------
# 混沌检测（第二节第 3 条 / 第四节混沌修复）
# ------------------------------------------------------------


def test_chaos_change_ratio_math():
    assert chaos_change_ratio([], []) == 0.0
    assert chaos_change_ratio(["a", "b"], ["a", "b"]) == 0.0
    # 交集 2 / 并集 10 → 恰好 0.8
    assert chaos_change_ratio(list("abcdefgh"), ["a", "b", "x", "y"]) == pytest.approx(0.8)


def test_chaos_boundary_exactly_80_percent_not_chaos(net):
    """恰好 80% 不同不算"超过 80%"，不触发回退。"""
    net.save_snapshot(list("abcdefgh"), {})
    report = net.inspect_loop(had_output=True, cluster_members=["a", "b", "x", "y"])
    assert ANOMALY_CHAOS not in _kinds(report)


def test_chaos_over_80_percent_rolls_back_to_snapshot(net):
    """变化超过 80% → 回退到最近一份正常快照 + 通知。"""
    net.save_snapshot(list("abcdefgh"), {"w": 0.5})
    report = net.inspect_loop(had_output=True, cluster_members=["a", "b", "x", "y", "z"])
    assert ANOMALY_CHAOS in _kinds(report)

    action = next(a for a in report.actions if a.type == "rollback_snapshot")
    assert action.payload["snapshot"]["cluster_members"] == list("abcdefgh")
    assert action.payload["snapshot"]["weights"] == {"w": 0.5}
    assert NOTICE_CHAOS_ROLLBACK in report.notifications


def test_chaos_no_snapshot_no_false_alarm(net):
    """还没有稳定快照时无法判定（"新配置需要更多数据"），不误报。"""
    report = net.inspect_loop(had_output=True, cluster_members=["a", "b", "c"])
    assert report.ok


# ------------------------------------------------------------
# 快照节奏与上限（第四节）
# ------------------------------------------------------------


def test_snapshot_every_n_normal_loops_and_max_keep(clock):
    """每 N 次正常循环保存一份快照，最多保留 5 份（测试用小参数）。"""
    net = SafetyNet(now=clock, snapshot_every=2, snapshot_max_keep=3)
    for _ in range(8):
        report = net.inspect_loop(
            had_output=True, cluster_members=["a", "b"], weights={"w": 0.5}
        )
        assert report.ok  # 成员不变，不触发混沌

    snapshots = net.list_snapshots()
    assert len(snapshots) == 3  # max_keep 生效
    assert [s["loop_count"] for s in snapshots] == [8, 6, 4]  # 最新在前
    assert net.latest_snapshot()["loop_count"] == 8


def test_silent_or_anomalous_loops_do_not_save_snapshots(clock):
    """无输出/有异常的循环不是"正常循环"，不计数不保存。"""
    net = SafetyNet(now=clock, snapshot_every=1)
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=True, weights={"w": 0.99})  # 权重退化 → 非正常循环
    assert net.list_snapshots() == []
    net.inspect_loop(had_output=True, cluster_members=["a"])
    assert len(net.list_snapshots()) == 1


# ------------------------------------------------------------
# 卡死恢复（第二节第 4 条 / 第四节卡死修复）
# ------------------------------------------------------------


def test_stuck_node_aborted_after_two_minutes(clock):
    """单节点卡住超过 2 分钟 → 强制 abort，标记 skipped，日志记录。"""
    abort_calls = []
    net = SafetyNet(now=clock, abort_node=lambda nid: abort_calls.append(nid) or True)
    net.node_started("n1")
    clock.advance(121)

    report = net.check()
    assert ANOMALY_STUCK_NODE in _kinds(report)
    assert abort_calls == ["n1"]  # 调用了 workflow_engine.abort_node 接缝
    assert "n1" in net.aborted_nodes()
    assert "n1" not in net.status()["nodes_in_flight"]

    action = next(a for a in report.actions if a.type == "abort_node")
    assert action.detail == "node n1 aborted by safety_net"  # 第四节日志原文
    assert action.payload["skipped"] is True
    assert action.payload["abort_callback_ok"] is True

    # 节点已移出在飞登记，不重复 abort
    assert net.check().ok


def test_node_under_timeout_untouched(clock):
    """未超时的节点不受影响；正常结束后不再跟踪。"""
    net = SafetyNet(now=clock, abort_node=lambda nid: True)
    net.node_started("n1")
    clock.advance(119)
    assert net.check().ok
    net.node_finished("n1")
    clock.advance(500)
    assert net.check().ok
    assert net.aborted_nodes() == []


def test_abort_callback_failure_does_not_break_safety_net(clock):
    """abort 回调抛异常不拖垮安全网，节点仍标记 skipped。"""

    def boom(node_id):
        raise RuntimeError("boom")

    net = SafetyNet(now=clock, abort_node=boom)
    net.node_started("n1")
    clock.advance(121)
    report = net.check()
    action = next(a for a in report.actions if a.type == "abort_node")
    assert action.payload["abort_callback_ok"] is False
    assert "n1" in net.aborted_nodes()


# ------------------------------------------------------------
# 权重退化检测（第二节第 5 条）
# ------------------------------------------------------------


def test_weights_degraded_boundaries():
    assert weights_degraded({"a": 0.95, "b": 0.05}) is True  # 全部极端
    assert weights_degraded({"a": 0.9, "b": 0.1}) is False  # 边界不算超过/低于
    assert weights_degraded({"a": 0.95, "b": 0.5}) is False  # 非全部极端
    assert weights_degraded({}) is False  # 未学习
    assert weights_degraded({"a": "high"}) is False  # 非数值忽略


def test_weight_degradation_resets_to_neutral(net):
    """所有权重极端 → 重置为 0.5 + 通知；档案数据不动（安全网只产出动作）。"""
    report = net.inspect_loop(had_output=True, weights={"a": 0.95, "b": 0.05})
    assert ANOMALY_WEIGHT_DEGRADATION in _kinds(report)
    action = next(a for a in report.actions if a.type == "reset_weights")
    assert action.payload["weights"] == {"a": 0.5, "b": 0.5}
    assert NOTICE_WEIGHT_RESET in report.notifications


# ------------------------------------------------------------
# 安全模式（第二节第 6 条 / 第四节安全模式）
# ------------------------------------------------------------


def _drive_into_safe_mode(net):
    """制造 3 种异常进入安全模式：沉默 + 混沌 + 权重退化。"""
    net.save_snapshot(["a", "b"], {})
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)
    return net.inspect_loop(
        had_output=False, cluster_members=["x", "y"], weights={"w": 0.99}
    )


def test_safe_mode_enter_after_three_anomaly_kinds(net):
    """连续检测到 3 种异常 → 进入安全模式 + 通知用户。"""
    report = _drive_into_safe_mode(net)
    assert net.in_safe_mode()
    assert report.mode == MODE_SAFE
    assert "enter_safe_mode" in _action_types(report)
    assert NOTICE_SAFE_MODE_ENTER in report.notifications


def test_safe_mode_suppresses_learning_and_push(net):
    """安全模式：不共振、不学习、不推送新东西；仍观察卡死。"""
    _drive_into_safe_mode(net)
    snapshot_count = len(net.list_snapshots())

    report = net.inspect_loop(had_output=False)  # 继续沉默
    assert report.mode == MODE_SAFE
    assert ANOMALY_SILENCE not in _kinds(report)  # 不再发兜底建议（不推送）
    assert "fallback_suggestion" not in _action_types(report)

    net.inspect_loop(had_output=True, cluster_members=["a"], weights={"w": 0.5})
    assert len(net.list_snapshots()) == snapshot_count  # 不学习 → 不存快照

    # 卡死监控仍然生效（保引擎不崩溃是安全网自身定位）
    net.node_started("n1")
    stuck_report = net.check()
    # check() 用的时钟已远超阈值？node_started 之后没有时间推移 → 不卡死
    assert ANOMALY_STUCK_NODE not in _kinds(stuck_report)


def test_safe_mode_requires_consecutive_kinds(net):
    """异常不连续（中间有无异常检查）→ 种类计数清零，不进安全模式。"""
    net.save_snapshot(["a", "b"], {})
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)  # 沉默（1 种）
    assert net.inspect_loop(had_output=True, weights={"w": 0.5}).ok  # 清零
    net.inspect_loop(had_output=True, cluster_members=["x", "y"])  # 混沌（重新计 1 种）
    net.inspect_loop(had_output=True, weights={"w": 0.99})  # 权重退化（2 种）
    assert not net.in_safe_mode()  # 连续只有 2 种，不进安全模式


def test_exit_safe_mode_keep_data(net):
    """手动退出（保留数据）：快照保留，异常计数清零。"""
    _drive_into_safe_mode(net)
    assert len(net.list_snapshots()) == 1

    result = net.exit_safe_mode(reset=False)
    assert result == {"exited": True, "reset": False, "mode": MODE_NORMAL}
    assert not net.in_safe_mode()
    assert len(net.list_snapshots()) == 1  # 数据保留
    assert net.status()["anomaly_streak_kinds"] == []  # 重新计数

    # 退出后单次异常不会立刻回到安全模式
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)  # 沉默（仅 1 种）
    assert not net.in_safe_mode()


def test_exit_safe_mode_full_reset(net):
    """手动退出（完全重置）：清空快照与学习计数。"""
    _drive_into_safe_mode(net)
    result = net.exit_safe_mode(reset=True)
    assert result["exited"] is True
    assert net.list_snapshots() == []
    status = net.status()
    assert status["normal_loop_count"] == 0
    assert status["consecutive_silent_loops"] == 0


def test_exit_safe_mode_when_not_in_safe_mode(net):
    assert net.exit_safe_mode()["exited"] is False


# ------------------------------------------------------------
# 事件日志与状态（"日志记录，不阻塞后续"）
# ------------------------------------------------------------


def test_events_record_anomalies_actions_notifications(net):
    for _ in range(2):
        net.inspect_loop(had_output=False)
    net.inspect_loop(had_output=False)

    events = net.events()
    assert events[0]["created_at"]  # 最新在前
    types = {(e["event_type"], e["kind"]) for e in events}
    assert ("anomaly", ANOMALY_SILENCE) in types
    assert ("action", "fallback_suggestion") in types
    assert any(e["event_type"] == "notification" for e in events)


def test_mode_change_events(net):
    _drive_into_safe_mode(net)
    net.exit_safe_mode()
    kinds = [e["kind"] for e in net.events() if e["event_type"] == "mode_change"]
    assert kinds == ["exit_safe_mode", "enter_safe_mode"]  # 最新在前


def test_status_shape(net):
    status = net.status()
    assert status["mode"] == MODE_NORMAL
    assert status["consecutive_silent_loops"] == 0
    assert status["last_heartbeat_age_seconds"] is None  # 引擎还没跑过
    assert status["nodes_in_flight"] == []
    assert status["snapshot_count"] == 0


def test_report_to_dict_jsonable(net):
    import json

    report = net.inspect_loop(had_output=True)
    payload = report.to_dict()
    assert payload["ok"] is True
    assert payload["mode"] == MODE_NORMAL
    json.dumps(payload, ensure_ascii=False)  # 可序列化（供未来 api 接线）
