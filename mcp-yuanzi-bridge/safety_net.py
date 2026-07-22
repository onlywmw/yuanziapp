#!/usr/bin/env python3
"""引擎安全网（DESIGN_ENGINE_SAFETY_NET.md）。

定位（文档题记）：引擎卡住、沉默、输出垃圾时的兜底。不是修原子，是保引擎不崩溃。
安全网是独立模块（文档末节）：不和引擎逻辑混在一起，只是观察引擎，在需要时介入。

与引擎的接线方式：
    net = SafetyNet()
    net.heartbeat()                 # 引擎每跑一次主循环调用（第二节第 1 条）
    report = net.inspect_loop(...)  # 每个循环结束做一次检查（第三节）
    report = net.check()            # 循环外巡检（心跳超时/卡死只能在这里发现）

文档要求、但引擎侧尚未提供的接缝（以注入解耦，星云引擎主循环落地后接线）：
- abort_node：卡死恢复时调用 workflow_engine.abort_node(node_id)（第四节卡死修复）。
  engine.py 当前没有该函数，因此构造时注入回调。
- 权重/集群配置的实际应用：安全网只产出动作（Action）与快照数据，由引擎执行。
- 通知送达：文档多处要求"通知用户"，通知文案由本模块生成并经 CheckReport/
  events() 输出；api.py 端点接线不在本轮范围。

持久化说明：文档要求"快照最多保留 5 份"与"日志记录"，未要求落库。本模块
用有界内存结构实现（快照 ≤5 份、事件 ≤500 条）。registry 侧迁移会改变
test_migrations.py 硬编码的版本清单，属于星云引擎主循环接线时的协调变更，
本轮不新增迁移文件。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional

from registry.schema import now_iso

logger = logging.getLogger(__name__)

# ============================================================
# 可配置常量（均出自 DESIGN_ENGINE_SAFETY_NET.md；文档未写死的已注明出处）
# ============================================================

HEARTBEAT_TIMEOUT_SECONDS = 30.0  # 第二节第 1 条：引擎 30 秒内应至少跑一次主循环
SILENCE_LOOP_THRESHOLD = 3  # 第二节第 2 条：连续 3 次循环无输出
CHAOS_CHANGE_THRESHOLD = 0.8  # 第二节第 3 条：集群成员变化超过 80%
STUCK_NODE_TIMEOUT_SECONDS = 120.0  # 第二节第 4 条：单节点卡住超过 2 分钟
WEIGHT_EXTREME_HIGH = 0.9  # 第二节第 5 条：超过 0.9 为极端高
WEIGHT_EXTREME_LOW = 0.1  # 第二节第 5 条：低于 0.1 为极端低
WEIGHT_RESET_VALUE = 0.5  # 第二节第 5 条：重置到初始值 0.5（中性）
ANOMALY_KIND_THRESHOLD = 3  # 第二节第 6 条：连续检测到 3 种异常 → 安全模式
SNAPSHOT_EVERY_N_LOOPS = 10  # 第四节：每 10 次正常循环保存一份快照
SNAPSHOT_MAX_KEEP = 5  # 第四节：快照最多保留 5 份

# 通知文案（原文照录文档，便于引擎/端侧直接透传）
NOTICE_CHAOS_ROLLBACK = "引擎暂时恢复为上次的设置。新配置需要更多数据。"  # 第二节第 3 条
NOTICE_WEIGHT_RESET = "引擎重新了解你。之前的数据不会丢，只是重新开始。"  # 第二节第 5 条
NOTICE_SAFE_MODE_ENTER = (
    "引擎进入安全模式。所有功能正常，但不做新推荐。你可以在设置中重置引擎。"
)  # 第二节第 6 条

# 兜底建议模板（第二节第 2 条 / 第四节沉默修复）
FALLBACK_SUGGESTION_TEMPLATE = "这个时间你通常在{behavior}。要试试吗？"
# 文档未给出无 rhythm 数据时的文案；取最保守、不让人困惑的说法
DEFAULT_SILENCE_MESSAGE = "现在没有新内容。你可以稍后回来看看。"

# 事件日志上限：文档只要求"日志记录"，未写死容量；取有界值防内存膨胀
EVENT_LOG_MAX_ENTRIES = 500

# 异常类别（第一节列出的四类故障 + 心跳超时）
ANOMALY_HEARTBEAT_TIMEOUT = "heartbeat_timeout"
ANOMALY_SILENCE = "silence"
ANOMALY_CHAOS = "chaos"
ANOMALY_STUCK_NODE = "stuck_node"
ANOMALY_WEIGHT_DEGRADATION = "weight_degradation"

MODE_NORMAL = "normal"
MODE_SAFE = "safe"


# ============================================================
# 报告数据结构
# ============================================================


@dataclass
class Anomaly:
    """一次检出的异常。kind 取 ANOMALY_* 常量。"""

    kind: str
    detail: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Action:
    """安全网采取的修复动作。payload 供引擎执行（回退快照/重置权重等）。"""

    type: str
    detail: str
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CheckReport:
    """一次检查的结果（第三节：每个循环结束做一次检查）。"""

    mode: str
    anomalies: List[Anomaly]
    actions: List[Action]
    notifications: List[str]
    generated_at: str

    @property
    def ok(self) -> bool:
        return not self.anomalies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "anomalies": [a.to_dict() for a in self.anomalies],
            "actions": [a.to_dict() for a in self.actions],
            "notifications": list(self.notifications),
            "generated_at": self.generated_at,
        }


# ============================================================
# 纯函数（模块级，便于复用与后续 api.py 接线）
# ============================================================


def chaos_change_ratio(reference: Iterable[Any], current: Iterable[Any]) -> float:
    """集群成员变化比例（第二节第 3 条）。

    文档只说"超过 80% 不同"，未定义算法；取 Jaccard 距离
    （1 - |交集| / |并集|）。两个集合都为空视为无变化。
    """
    ref, cur = set(reference), set(current)
    union = ref | cur
    if not union:
        return 0.0
    return 1.0 - len(ref & cur) / len(union)


def weights_degraded(weights: Dict[str, Any]) -> bool:
    """权重退化判定（第二节第 5 条）：所有权重都超过 0.9 或低于 0.1。

    按字面取"每个权重均落在 [0.1, 0.9] 之外"（混合极端也算学到极端值）。
    恰为 0.9 / 0.1 不算（"超过"/"低于"不含边界）；空权重表视为未学习。
    """
    values = [
        v
        for v in weights.values()
        if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    if not values:
        return False
    return all(v > WEIGHT_EXTREME_HIGH or v < WEIGHT_EXTREME_LOW for v in values)


def current_period(now: Optional[datetime] = None) -> str:
    """由当前时间推出 person-atom rhythm 的时段键（DESIGN_PERSON_ATOM.md 第五节）。

    文档示例键为 <weekday|weekend>_<时段>（morning/afternoon 出自示例，
    evening/night 按同一命名规则延伸，文档未列全）。
    """
    now = now or datetime.now()
    day = "weekend" if now.weekday() >= 5 else "weekday"
    hour = now.hour
    if 5 <= hour < 12:
        part = "morning"
    elif 12 <= hour < 18:
        part = "afternoon"
    elif 18 <= hour < 23:
        part = "evening"
    else:
        part = "night"
    return f"{day}_{part}"


def _extract_behavior(entry: Any) -> Optional[str]:
    """从 rhythm 某时段的取值里提取"历史高频行为"。容忍三种形态：

    - {"behavior": "听歌", ...}        显式行为键（behavior/activity/action）
    - {"听歌": 12, "阅读": 3}          数值取值视为频次，取最高
    - ["听歌", "阅读", "听歌"]         列表取最高频（并列取先出现）
    其余形态（如 DESIGN_PERSON_ATOM 示例的 aspect 字典）无法识别行为，返回 None。
    """
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        for key in ("behavior", "activity", "action"):
            value = entry.get(key)
            if isinstance(value, str) and value:
                return value
        numeric = {
            k: v
            for k, v in entry.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if numeric:
            return max(numeric, key=numeric.get)
        return None
    if isinstance(entry, (list, tuple)):
        counts: Dict[Any, int] = {}
        for item in entry:
            counts[item] = counts.get(item, 0) + 1
        if counts:
            return max(counts, key=counts.get)
    return None


def pick_rhythm_behavior(
    person_atom: Optional[Dict[str, Any]], period: Optional[str]
) -> Optional[str]:
    """从 person-atom 的 rhythm 字段找当前时段的历史高频行为（第四节沉默修复）。"""
    if not person_atom or not period:
        return None
    rhythm = person_atom.get("rhythm")
    if not isinstance(rhythm, dict):
        return None
    return _extract_behavior(rhythm.get(period))


def build_fallback_suggestion(
    person_atom: Optional[Dict[str, Any]] = None, period: Optional[str] = None
) -> str:
    """生成一句话兜底建议（第二节第 2 条模板）。

    不共振、不聚类，只用最简单的方式给用户一个选项（第四节）；
    找不到 rhythm 数据时退回最保守的默认文案。
    """
    behavior = pick_rhythm_behavior(person_atom, period or current_period())
    if behavior:
        return FALLBACK_SUGGESTION_TEMPLATE.format(behavior=behavior)
    return DEFAULT_SILENCE_MESSAGE


# ============================================================
# 安全网本体
# ============================================================


class SafetyNet:
    """观察引擎、按需介入的独立安全网（DESIGN_ENGINE_SAFETY_NET.md 全文）。

    参数均为文档阈值的注入口，缺省取模块级常量；now/abort_node 是测试与
    引擎接线的接缝（now 取单调时钟，便于 hermetic 测试）。
    """

    def __init__(
        self,
        *,
        now: Callable[[], float] = time.monotonic,
        abort_node: Optional[Callable[[str], bool]] = None,
        heartbeat_timeout: float = HEARTBEAT_TIMEOUT_SECONDS,
        silence_threshold: int = SILENCE_LOOP_THRESHOLD,
        chaos_threshold: float = CHAOS_CHANGE_THRESHOLD,
        stuck_timeout: float = STUCK_NODE_TIMEOUT_SECONDS,
        anomaly_kind_threshold: int = ANOMALY_KIND_THRESHOLD,
        snapshot_every: int = SNAPSHOT_EVERY_N_LOOPS,
        snapshot_max_keep: int = SNAPSHOT_MAX_KEEP,
    ) -> None:
        self._now = now
        self._abort_node = abort_node
        self._heartbeat_timeout = heartbeat_timeout
        self._silence_threshold = silence_threshold
        self._chaos_threshold = chaos_threshold
        self._stuck_timeout = stuck_timeout
        self._anomaly_kind_threshold = anomaly_kind_threshold
        self._snapshot_every = snapshot_every
        self._snapshot_max_keep = snapshot_max_keep

        self._mode = MODE_NORMAL
        self._last_heartbeat: Optional[float] = None  # 引擎还没跑过 → 不判超时
        self._heartbeat_timed_out = False  # 同一段超时只报一次，心跳后解除
        self._consecutive_silent_loops = 0
        self._normal_loop_count = 0
        # 连续检出异常的类别（未去重）；一次无异常检查即清零
        self._anomaly_streak: List[str] = []
        self._nodes_in_flight: Dict[str, float] = {}  # node_id -> 开始时刻
        self._aborted_nodes: List[str] = []
        self._snapshots: List[Dict[str, Any]] = []  # 旧 → 新
        self._events: Deque[Dict[str, Any]] = deque(maxlen=EVENT_LOG_MAX_ENTRIES)

    # ---------------- 状态查询 ----------------

    @property
    def mode(self) -> str:
        return self._mode

    def in_safe_mode(self) -> bool:
        return self._mode == MODE_SAFE

    def aborted_nodes(self) -> List[str]:
        return list(self._aborted_nodes)

    def status(self) -> Dict[str, Any]:
        """安全网当前状态快照（供引擎监控/未来 api.py 端点使用）。"""
        now = self._now()
        return {
            "mode": self._mode,
            "consecutive_silent_loops": self._consecutive_silent_loops,
            "normal_loop_count": self._normal_loop_count,
            "last_heartbeat_age_seconds": (
                round(now - self._last_heartbeat, 1)
                if self._last_heartbeat is not None
                else None
            ),
            "heartbeat_timed_out": self._heartbeat_timed_out,
            "nodes_in_flight": sorted(self._nodes_in_flight),
            "aborted_nodes": list(self._aborted_nodes),
            "snapshot_count": len(self._snapshots),
            "anomaly_streak_kinds": sorted(set(self._anomaly_streak)),
        }

    def events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """事件日志（最新在前）：anomaly / action / notification / mode_change。"""
        return list(self._events)[-limit:][::-1]

    # ---------------- 引擎侧上报接口 ----------------

    def heartbeat(self) -> None:
        """引擎主循环每跑一次调用一次（第二节第 1 条）。"""
        self._last_heartbeat = self._now()
        self._heartbeat_timed_out = False

    def node_started(self, node_id: str) -> None:
        """登记工作流节点开始执行（第二节第 4 条卡死检测的依据）。"""
        self._nodes_in_flight[node_id] = self._now()

    def node_finished(self, node_id: str) -> None:
        """节点正常结束，移出在飞登记。"""
        self._nodes_in_flight.pop(node_id, None)

    # ---------------- 检查入口（第三节） ----------------

    def inspect_loop(
        self,
        *,
        had_output: bool,
        cluster_members: Optional[Iterable[Any]] = None,
        weights: Optional[Dict[str, Any]] = None,
        person_atom: Optional[Dict[str, Any]] = None,
        period: Optional[str] = None,
    ) -> CheckReport:
        """每个循环结束做一次检查（第三节，按文档列出的顺序逐项判定）。"""
        self.heartbeat()
        anomalies: List[Anomaly] = []
        actions: List[Action] = []
        notifications: List[str] = []

        if had_output:
            self._consecutive_silent_loops = 0
        else:
            self._consecutive_silent_loops += 1

        if self._mode == MODE_SAFE:
            # 安全模式（第二节第 6 条）：不共振、不学习、不推送新东西，
            # 因此沉默/混沌/权重检查全部关闭；仍观察卡死——"保引擎不崩溃"
            # 是安全网自身的定位（文档题记）。
            self._check_stuck_nodes(anomalies, actions)
            self._record_inspection_events(anomalies, actions, notifications)
            return self._report(anomalies, actions, notifications)

        # 1) 主循环超时：本方法在循环末尾调用，心跳刚刷新，超时只在 check() 判定。

        # 2) 沉默兜底（第二节第 2 条）
        if self._consecutive_silent_loops >= self._silence_threshold:
            anomalies.append(
                Anomaly(
                    ANOMALY_SILENCE,
                    f"连续 {self._consecutive_silent_loops} 次循环无输出",
                )
            )
            suggestion = build_fallback_suggestion(person_atom, period)
            actions.append(
                Action(
                    "fallback_suggestion",
                    "沉默兜底：用最简单的规则给用户一个选项",
                    {"message": suggestion},
                )
            )
            notifications.append(suggestion)

        # 3) 混沌检测（第二节第 3 条）：与最近一份正常快照比较；
        #    还没有快照时无法判定（正对应"新配置需要更多数据"），不误报。
        if cluster_members is not None:
            members = list(cluster_members)
            snapshot = self.latest_snapshot()
            if snapshot is not None:
                ratio = chaos_change_ratio(snapshot["cluster_members"], members)
                if ratio > self._chaos_threshold:
                    anomalies.append(
                        Anomaly(
                            ANOMALY_CHAOS,
                            f"集群成员变化 {ratio:.0%}（阈值 {self._chaos_threshold:.0%}）",
                        )
                    )
                    # 第四节混沌修复：回退到最近一份正常快照 + 通知
                    actions.append(
                        Action(
                            "rollback_snapshot",
                            "回退到最近一份正常快照（集群成员 + 权重）",
                            {"snapshot": snapshot},
                        )
                    )
                    notifications.append(NOTICE_CHAOS_ROLLBACK)

        # 4) 卡死恢复（第二节第 4 条）
        self._check_stuck_nodes(anomalies, actions)

        # 5) 权重退化检测（第二节第 5 条）
        if weights and weights_degraded(weights):
            anomalies.append(
                Anomaly(ANOMALY_WEIGHT_DEGRADATION, "所有权重均超出 [0.1, 0.9]")
            )
            # 第四节权重退化修复：全部重置为 0.5，保留档案数据不丢历史
            actions.append(
                Action(
                    "reset_weights",
                    "全部权重重置为 0.5（保留原始档案数据，只重置权重）",
                    {"weights": {k: WEIGHT_RESET_VALUE for k in weights}},
                )
            )
            notifications.append(NOTICE_WEIGHT_RESET)

        # 6) 异常计数 → 安全模式（第二节第 6 条）
        self._update_streak_and_maybe_enter_safe_mode(anomalies, actions, notifications)

        # 第四节：每 10 次"正常循环"保存一份快照（集群成员 + 权重）。
        # 文档未定义"正常循环"，本实现取"有输出且本次检查无异常"的循环；
        # 安全模式下不学习（第二节第 6 条），不会走到这里。
        if had_output and not anomalies:
            self._normal_loop_count += 1
            if self._normal_loop_count % self._snapshot_every == 0 and (
                cluster_members is not None or weights is not None
            ):
                self.save_snapshot(cluster_members or [], weights or {})

        self._record_inspection_events(anomalies, actions, notifications)
        return self._report(anomalies, actions, notifications)

    def check(self) -> CheckReport:
        """循环外巡检：心跳超时（第 1 条）与卡死（第 4 条）只能在这里发现。"""
        anomalies: List[Anomaly] = []
        actions: List[Action] = []
        notifications: List[str] = []
        now = self._now()

        # 心跳检测（第二节第 1 条）。引擎从未跑过循环时不判超时；
        # 同一段超时只报一次（_heartbeat_timed_out），心跳恢复后解除。
        if (
            self._last_heartbeat is not None
            and not self._heartbeat_timed_out
            and now - self._last_heartbeat > self._heartbeat_timeout
        ):
            self._heartbeat_timed_out = True
            age = now - self._last_heartbeat
            # "超时 → 检查哪个环节卡住了"：附在飞节点与已运行时长作诊断
            in_flight = {
                nid: round(now - started, 1)
                for nid, started in self._nodes_in_flight.items()
            }
            anomalies.append(
                Anomaly(
                    ANOMALY_HEARTBEAT_TIMEOUT,
                    f"主循环 {age:.0f}s 未运行（阈值 {self._heartbeat_timeout:.0f}s）",
                )
            )
            # 第三节：记录 + 重置循环
            actions.append(
                Action("reset_loop", "记录超时并重置主循环", {"in_flight_nodes": in_flight})
            )

        self._check_stuck_nodes(anomalies, actions)

        if self._mode != MODE_SAFE:
            self._update_streak_and_maybe_enter_safe_mode(
                anomalies, actions, notifications
            )
        self._record_inspection_events(anomalies, actions, notifications)
        return self._report(anomalies, actions, notifications)

    # ---------------- 修复机制（第四节） ----------------

    def save_snapshot(
        self, cluster_members: Iterable[Any], weights: Dict[str, Any]
    ) -> Dict[str, Any]:
        """保存一份稳定配置快照（集群成员 + 权重），最多保留 5 份。"""
        members = list(cluster_members)
        try:
            members = sorted(members)
        except TypeError:
            pass  # 成员类型不可比时按原顺序保存
        snapshot = {
            "loop_count": self._normal_loop_count,
            "cluster_members": members,
            "weights": dict(weights),
            "created_at": now_iso(),
        }
        self._snapshots.append(snapshot)
        if self._snapshot_max_keep > 0:
            del self._snapshots[: -self._snapshot_max_keep]
        return dict(snapshot)

    def latest_snapshot(self) -> Optional[Dict[str, Any]]:
        """最近一份正常快照（混沌修复的回退目标）。"""
        if not self._snapshots:
            return None
        return self._copy_snapshot(self._snapshots[-1])

    def list_snapshots(self) -> List[Dict[str, Any]]:
        """全部存活快照（最新在前）。"""
        return [self._copy_snapshot(s) for s in reversed(self._snapshots)]

    @staticmethod
    def _copy_snapshot(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "loop_count": snapshot["loop_count"],
            "cluster_members": list(snapshot["cluster_members"]),
            "weights": dict(snapshot["weights"]),
            "created_at": snapshot["created_at"],
        }

    def exit_safe_mode(self, reset: bool = False) -> Dict[str, Any]:
        """用户在设置中手动退出安全模式（第二节第 6 条 / 第四节）。

        reset=False 保留数据（快照与学习计数保留）；
        reset=True  完全重置（清空快照与学习计数，重新了解用户）。
        """
        if self._mode != MODE_SAFE:
            return {"exited": False, "reason": "not_in_safe_mode", "mode": self._mode}
        self._mode = MODE_NORMAL
        self._anomaly_streak.clear()
        if reset:
            self._snapshots.clear()
            self._normal_loop_count = 0
            self._consecutive_silent_loops = 0
        detail = "完全重置（清空快照与学习计数）" if reset else "保留数据"
        self._record_event("mode_change", "exit_safe_mode", detail)
        return {"exited": True, "reset": reset, "mode": self._mode}

    # ---------------- 内部 ----------------

    def _check_stuck_nodes(
        self, anomalies: List[Anomaly], actions: List[Action]
    ) -> None:
        """卡死恢复（第二节第 4 条 / 第四节）：单节点卡住超过 2 分钟 →
        强制 abort，标记 skipped，不阻塞后续，日志记录。"""
        now = self._now()
        for node_id, started in list(self._nodes_in_flight.items()):
            age = now - started
            if age <= self._stuck_timeout:
                continue
            anomalies.append(
                Anomaly(
                    ANOMALY_STUCK_NODE,
                    f"工作流节点 {node_id} 卡住 {age:.0f}s（阈值 {self._stuck_timeout:.0f}s）",
                )
            )
            callback_ok: Optional[bool] = None
            if self._abort_node is not None:
                try:
                    callback_ok = bool(self._abort_node(node_id))
                except Exception:  # noqa: BLE001 - abort 失败不拖垮安全网
                    logger.exception("abort_node callback raised for %s", node_id)
                    callback_ok = False
            del self._nodes_in_flight[node_id]
            self._aborted_nodes.append(node_id)
            # 第四节：日志记录 "node X aborted by safety_net"
            detail = f"node {node_id} aborted by safety_net"
            logger.warning(detail)
            actions.append(
                Action(
                    "abort_node",
                    detail,
                    {
                        "node_id": node_id,
                        "skipped": True,
                        "abort_callback_ok": callback_ok,
                    },
                )
            )

    def _update_streak_and_maybe_enter_safe_mode(
        self,
        anomalies: List[Anomaly],
        actions: List[Action],
        notifications: List[str],
    ) -> None:
        """安全模式判定（第二节第 6 条）：连续检测到 3 种异常 → 进入安全模式。

        按"种类"计数（set）；一次无异常检查即清零（"连续"）。
        第三节写"异常计数 > 3"，第二节写"3 种异常"，取更具体的后者。
        """
        if not anomalies:
            self._anomaly_streak.clear()
            return
        self._anomaly_streak.extend(a.kind for a in anomalies)
        kinds = set(self._anomaly_streak)
        if len(kinds) >= self._anomaly_kind_threshold and self._mode != MODE_SAFE:
            self._mode = MODE_SAFE
            detail = "连续检测到异常: " + ", ".join(sorted(kinds))
            self._record_event("mode_change", "enter_safe_mode", detail)
            actions.append(Action("enter_safe_mode", detail))
            notifications.append(NOTICE_SAFE_MODE_ENTER)

    def _report(
        self,
        anomalies: List[Anomaly],
        actions: List[Action],
        notifications: List[str],
    ) -> CheckReport:
        return CheckReport(
            mode=self._mode,
            anomalies=anomalies,
            actions=actions,
            notifications=notifications,
            generated_at=now_iso(),
        )

    def _record_inspection_events(
        self,
        anomalies: List[Anomaly],
        actions: List[Action],
        notifications: List[str],
    ) -> None:
        for anomaly in anomalies:
            self._record_event("anomaly", anomaly.kind, anomaly.detail)
        for action in actions:
            self._record_event("action", action.type, action.detail)
        for message in notifications:
            self._record_event("notification", None, message)

    def _record_event(
        self, event_type: str, kind: Optional[str], detail: str
    ) -> None:
        self._events.append(
            {
                "event_type": event_type,
                "kind": kind,
                "detail": detail,
                "created_at": now_iso(),
            }
        )
