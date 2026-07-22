"""连接原子：版本约束 / 自动匹配 / 匹配接口 / implements 审核校验测试
（DESIGN_CONNECTOR_ATOM.md §三「自动匹配」/§四「Schema 与 implements 校验」）。

覆盖四组契约：
- connectors.version_satisfies：>=,>,<=,<,== 与裸版本号，数字段补零，
  空约束恒真，非法输入恒假；
- connectors.match_connector：四条硬过滤（os / os_version / manufacturer /
  hardware）+ 生命周期口径（只 registered/running 参与）+ 排序层级
  （0. manufacturer 精确 > "*" → 1. schema_version 新优先（数字段比较，
  缺失视为最低）→ 2. 使用人数（恒 0 兜底）→ 3. 评分高优先 →
  4. preferred=true 优先 → 5. atom_id 字典序兜底）+ limit + 空结果；
  另覆盖 compatibility / schema_version 经 submit_atom 顶层字段镜像进
  classification 并驱动匹配/排序；返回项含 schema_version 与 preferred 两键；
- GET /connectors/match：200 形状 {device, function, candidates}、
  缺 function 422、查询参数覆盖环境变量探测值；
- implements 审核校验（review_atom 批准路径）：标准不存在 / 目标非 schema
  → implements_unknown_schema；输出缺键 / 类型不一致 → implements_mismatch；
  完全匹配正常 registered；无 implements 零影响。

全部 hermetic：match_connector 用例跑内存库；API 用例库文件、账本与链数据
目录均落 tmp_path，不读仓库内真实 registry.db、不触网。
"""

from __future__ import annotations

import json
import sqlite3

import pytest

import connectors
from api import create_app
from auth import create_token
from fastapi.testclient import TestClient
from migrations import migrate
from registry import review_atom, set_atom_status, submit_atom

ADMIN_TOKEN = "admin-secret"
VIEWER_TOKEN = "viewer-secret"

# 本设备画像：Android 12 / 三星 / 有 gps+camera（无 lidar）
DEVICE = {
    "os": "android",
    "os_version": "12",
    "manufacturer": "samsung",
    "hardware": ["gps", "camera"],
}


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _connector_atom(
    atom_id,
    *,
    compat=None,
    implements=None,
    io=None,
    domain=None,
    arch_type="external",
    output_schema=None,
    schema_version=None,
    preferred=None,
):
    """最小合法连接器/接口标准原子；function 名按 atom_id 派生，避免签名去重冲突。"""
    atom = {
        "atom_id": atom_id,
        "name": atom_id,
        "version": "1.0.0",
        "description": "",
        "purpose": {
            "functions": [
                {"name": "f_" + atom_id.replace(".", "_").replace("-", "_")}
            ]
        },
        "architecture": {
            "type": arch_type,
            "runtime": "python3.10",
            "dependencies": [],
        },
        "ownership": {"author": "tester", "license": "MIT"},
        "lifecycle": {"status": "submitted"},
    }
    if domain is not None:
        atom["classification"] = {"category": "connector", "domain": domain}
    if output_schema is not None:
        atom["purpose"]["functions"][0]["output_schema"] = output_schema
    if compat is not None:
        atom["compatibility"] = compat
    if implements is not None:
        atom["implements"] = implements
    if io is not None:
        atom["io"] = io
    if schema_version is not None:
        atom["schema_version"] = schema_version
    if preferred is not None:
        atom["preferred"] = preferred
    return atom


def _register(conn, atom, *, score=None):
    """submit + 审核批准（registered）；score 写入 review_result 供排序断言。"""
    result = submit_atom(conn, atom, actor="test")
    assert result["success"], result
    res = review_atom(
        conn, atom["atom_id"], approved=True, reviewer="test-reviewer", score=score
    )
    assert res["status"] == "registered", res


@pytest.fixture()
def conn():
    c = sqlite3.connect(":memory:")
    migrate(c)
    yield c
    c.close()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("YUANZI_API_TOKEN", raising=False)
    monkeypatch.setenv("YUANZI_NOTARIZE_SYNC", "1")  # 同步公证，测试确定性
    # hermetic：账本与链数据一律落 tmp_path，绝不碰仓库内真实数据
    monkeypatch.delenv("NOTARY_PROVIDER", raising=False)
    monkeypatch.setenv("NOTARY_LEDGER_PATH", str(tmp_path / "notary_ledger.jsonl"))
    monkeypatch.setenv("YUANZI_CHAIN_HOME", str(tmp_path / "yuanzi_chain_home"))
    monkeypatch.delenv("YUANZI_CHAIN_REPO", raising=False)
    # 设备探测环境变量默认清空，保证 device 字段确定性；各用例按需自行设定
    for name in (
        connectors.ENV_DEVICE_OS,
        connectors.ENV_DEVICE_OS_VERSION,
        connectors.ENV_DEVICE_MANUFACTURER,
        connectors.ENV_DEVICE_HARDWARE,
    ):
        monkeypatch.delenv(name, raising=False)
    db = tmp_path / "connectors.db"
    setup = sqlite3.connect(str(db))
    migrate(setup)
    create_token(setup, ADMIN_TOKEN, role="admin")
    create_token(setup, VIEWER_TOKEN, role="viewer")
    setup.close()
    with TestClient(create_app(db)) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. version_satisfies：版本约束比较（契约 4）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "version,constraint,expected",
    [
        # >= 家族：满足 / 边界 / 不满足
        ("12", ">=11", True),
        ("11", ">=11", True),
        ("10", ">=11", False),
        # > 严格大于
        ("12", ">11", True),
        ("11", ">11", False),
        # <= 家族
        ("10", "<=11", True),
        ("11", "<=11", True),
        ("12", "<=11", False),
        # < 严格小于
        ("10", "<11", True),
        ("11", "<11", False),
        # == 与裸版本号（裸版本按 == 处理）
        ("11", "==11", True),
        ("12", "==11", False),
        ("11", "11", True),
        ("12", "11", False),
        # 多段补零：短的一侧补 0 后逐段比较
        ("11.0", "11", True),
        ("11", "11.0.0", True),
        ("11.2", ">=11.1.0", True),
        ("11.0.5", ">11", True),
        # 空约束视为无约束，恒 True
        ("12", "", True),
        ("12", "   ", True),
        ("12", None, True),
        # 非法输入恒 False：空 version / 无法解析的任一侧 / 算子后无版本
        ("", ">=11", False),
        (None, ">=11", False),
        ("abc", ">=11", False),
        ("12", ">=x", False),
        ("12", ">=", False),
    ],
)
def test_version_satisfies(version, constraint, expected):
    assert connectors.version_satisfies(version, constraint) is expected


# ---------------------------------------------------------------------------
# 2. match_connector：硬过滤 / 排序 / limit / 空结果 / compatibility 镜像
# ---------------------------------------------------------------------------


def test_match_connector_hard_filters(conn):
    """os 不符、版本不满足、manufacturer 精确不符、硬件缺失、非 registered/running 一律被滤。"""
    # 合格：registered，全部条件满足
    _register(
        conn,
        _connector_atom(
            "connector.location-ok",
            compat={
                "os": "android",
                "os_version": ">=11",
                "manufacturer": "*",
                "hardware": ["gps"],
            },
        ),
        score=5.0,
    )
    # 合格：registered → running（探测在线同样参与匹配）
    _register(
        conn,
        _connector_atom(
            "connector.location-live",
            compat={"os": "android", "manufacturer": "*"},
        ),
        score=3.0,
    )
    assert set_atom_status(conn, "connector.location-live", "running")["success"]
    # 被滤：os 不符（评分再高也不参与）
    _register(
        conn,
        _connector_atom(
            "connector.location-wrong-os",
            compat={"os": "ios", "manufacturer": "*"},
        ),
        score=9.9,
    )
    # 被滤：设备版本 12 不满足 >=13
    _register(
        conn,
        _connector_atom(
            "connector.location-low-version",
            compat={"os": "android", "os_version": ">=13"},
        ),
    )
    # 被滤：manufacturer 精确值 xiaomi ≠ samsung
    _register(
        conn,
        _connector_atom(
            "connector.location-other-vendor",
            compat={"os": "android", "manufacturer": "xiaomi"},
        ),
    )
    # 被滤：需要 lidar，本机硬件不含（hardware 非子集）
    _register(
        conn,
        _connector_atom(
            "connector.location-need-lidar",
            compat={"os": "android", "hardware": ["gps", "lidar"]},
        ),
    )
    # 被滤：仍处 submitted（未审核）
    result = submit_atom(
        conn,
        _connector_atom(
            "connector.location-pending",
            compat={"os": "android", "manufacturer": "*"},
        ),
        actor="test",
    )
    assert result["success"], result
    # 被滤：审核拒绝 rejected
    result = submit_atom(
        conn,
        _connector_atom(
            "connector.location-denied",
            compat={"os": "android", "manufacturer": "*"},
        ),
        actor="test",
    )
    assert result["success"], result
    assert (
        review_atom(conn, "connector.location-denied", approved=False)["status"]
        == "rejected"
    )

    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-ok",
        "connector.location-live",
    ]


def test_match_connector_sorting_contract(conn):
    """排序层级钉死（DESIGN_CONNECTOR_ATOM.md §四「自动匹配优先级」）：
    0. manufacturer 精确 > "*"（保留层，设备厂商通路优先，精确低版本低分仍靠前）；
    1. schema_version 新优先：数字段比较（"1.10.0" > "1.9.0"），缺失视为最低；
    2. 使用人数多优先（数据模型无字段，恒 0 兜底，不可测决胜）；
    3. 社区评分高优先（仅在同版本时决胜）；
    4. preferred=true 优先（仅在同版本同分时决胜）；
    5. atom_id 字典序兜底。
    """
    # tier0：manufacturer 精确匹配，即使版本最旧、评分最低也排第一
    _register(
        conn,
        _connector_atom(
            "connector.location-sam",
            compat={"os": "android", "manufacturer": "samsung"},
            schema_version="1.0.0",
        ),
        score=1.0,
    )
    # tier1：通配档内 schema_version 压评分——"1.10.0" 评分 5 排在
    # "1.9.0" 评分 9 之前（同时覆盖数字段比较：字典序下 "1.10.0" < "1.9.0"）
    _register(
        conn,
        _connector_atom(
            "connector.location-v110",
            compat={"os": "android", "manufacturer": "*"},
            schema_version="1.10.0",
        ),
        score=5.0,
    )
    _register(
        conn,
        _connector_atom(
            "connector.location-v19",
            compat={"os": "android", "manufacturer": "*"},
            schema_version="1.9.0",
        ),
        score=9.0,
    )
    # 缺失 schema_version 视为最低（空版本），评分 10 也排最后
    _register(
        conn,
        _connector_atom(
            "connector.location-nover",
            compat={"os": "android", "manufacturer": "*"},
        ),
        score=10.0,
    )

    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-sam",  # tier0：厂商精确通路优先
        "connector.location-v110",  # tier1：版本新压评分
        "connector.location-v19",
        "connector.location-nover",  # 缺失版本视为最低
    ]
    assert [c["manufacturer_match"] for c in results] == [
        "exact",
        "any",
        "any",
        "any",
    ]
    assert [c["score"] for c in results] == [1.0, 5.0, 9.0, 10.0]
    # 返回项新增 schema_version（字符串或 None）与 preferred（布尔）两键
    assert [c["schema_version"] for c in results] == [
        "1.0.0",
        "1.10.0",
        "1.9.0",
        None,
    ]
    assert [c["preferred"] for c in results] == [False, False, False, False]
    # 返回项形状钉死：既有四键保留，新增两键，排序专用键（_usage）不外泄
    for item in results:
        assert set(item) == {
            "atom_id",
            "manufacturer_match",
            "score",
            "compatibility",
            "schema_version",
            "preferred",
        }


def test_match_connector_schema_version_compares_numeric_segments(conn):
    """"1.10.0" > "1.9.0"：按数字段比较，防字典序陷阱。

    字典序下 "1.10.0" < "1.9.0"（'1' < '9'）；此处让 1.9.0 一方 atom_id
    字典序更小，若实现误用字符串比较或漏掉版本层，顺序都会翻。
    """
    compat = {"os": "android", "manufacturer": "*"}
    _register(
        conn,
        _connector_atom(
            "connector.location-a", compat=compat, schema_version="1.9.0"
        ),
        score=8.0,
    )
    _register(
        conn,
        _connector_atom(
            "connector.location-b", compat=compat, schema_version="1.10.0"
        ),
        score=8.0,
    )
    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-b",
        "connector.location-a",
    ]


def test_match_connector_preferred_breaks_tie_at_same_version_and_score(conn):
    """preferred=true 在同版本同分时决胜（tier4）；缺失与 false 同为不优先档，
    档内按 atom_id 字典序兜底。"""
    compat = {"os": "android", "manufacturer": "*"}
    _register(
        conn,
        _connector_atom(
            "connector.location-a-nopref", compat=compat, schema_version="1.2.0"
        ),
        score=8.0,
    )
    _register(
        conn,
        _connector_atom(
            "connector.location-b-plain",
            compat=compat,
            schema_version="1.2.0",
            preferred=False,
        ),
        score=8.0,
    )
    # atom_id 字典序最大，靠 preferred=true 压过前面两个
    _register(
        conn,
        _connector_atom(
            "connector.location-z-pref",
            compat=compat,
            schema_version="1.2.0",
            preferred=True,
        ),
        score=8.0,
    )

    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-z-pref",
        "connector.location-a-nopref",
        "connector.location-b-plain",
    ]
    assert [c["preferred"] for c in results] == [True, False, False]


def test_match_connector_preferred_adds_no_boost_beyond_tier4(conn):
    """preferred 不加分：版本更旧或评分更低时，preferred=true 照样排后。"""
    compat = {"os": "android", "manufacturer": "*"}
    _register(
        conn,
        _connector_atom(
            "connector.location-pref",
            compat=compat,
            schema_version="1.0.0",
            preferred=True,
        ),
        score=5.0,
    )
    # 同版本、评分更高、无 preferred：评分层（tier3）先于 preferred 层（tier4）
    _register(
        conn,
        _connector_atom(
            "connector.location-hi-score", compat=compat, schema_version="1.0.0"
        ),
        score=6.0,
    )
    # 版本更新、评分更低、无 preferred：版本层（tier1）最优先
    _register(
        conn,
        _connector_atom(
            "connector.location-v2", compat=compat, schema_version="2.0.0"
        ),
        score=1.0,
    )

    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-v2",
        "connector.location-hi-score",
        "connector.location-pref",
    ]


def test_match_connector_limit_truncates_results(conn):
    """limit 截断：只返回排序后的前 N 个候选。"""
    for suffix, score in (("a", 9.0), ("b", 5.0), ("c", 1.0)):
        _register(
            conn,
            _connector_atom(
                f"connector.location-{suffix}",
                compat={"os": "android", "manufacturer": "*"},
            ),
            score=score,
        )
    results = connectors.match_connector(conn, "location", DEVICE, limit=2)
    assert [c["atom_id"] for c in results] == [
        "connector.location-a",
        "connector.location-b",
    ]


def test_match_connector_no_candidates_returns_empty(conn):
    """空库与无匹配功能均返回空列表。"""
    assert connectors.match_connector(conn, "location", DEVICE) == []
    _register(
        conn,
        _connector_atom(
            "connector.location-ok",
            compat={"os": "android", "manufacturer": "*"},
        )
    )
    assert connectors.match_connector(conn, "sonar", DEVICE) == []


def test_submit_mirrors_top_level_compatibility_into_classification(conn):
    """顶层 compatibility 经 submit_atom 镜像进 classification_json，并驱动设备匹配。"""
    compat = {
        "os": "android",
        "os_version": ">=11",
        "manufacturer": "samsung",
        "hardware": ["gps"],
    }
    atom = _connector_atom("connector.location-mirror", compat=compat)
    result = submit_atom(conn, atom, actor="test")
    assert result["success"], result

    row = conn.execute(
        "SELECT classification_json FROM atom_registry WHERE atom_id = ?",
        ("connector.location-mirror",),
    ).fetchone()
    classification = json.loads(row[0])
    assert classification["compatibility"] == compat

    # 镜像值即匹配依据：审核批准后按 compatibility 命中本设备
    res = review_atom(conn, "connector.location-mirror", approved=True, score=7.0)
    assert res["status"] == "registered"
    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == ["connector.location-mirror"]
    assert results[0]["compatibility"] == compat
    assert results[0]["manufacturer_match"] == "exact"


def test_submit_mirrors_top_level_schema_version_into_classification(conn):
    """顶层 schema_version 经 submit_atom 镜像进 classification_json，并驱动排序
    （与 implements/compatibility 同款镜像惯例）。"""
    compat = {"os": "android", "manufacturer": "*"}
    atom = _connector_atom(
        "connector.location-v2", compat=compat, schema_version="2.0.0"
    )
    result = submit_atom(conn, atom, actor="test")
    assert result["success"], result

    row = conn.execute(
        "SELECT classification_json FROM atom_registry WHERE atom_id = ?",
        ("connector.location-v2",),
    ).fetchone()
    classification = json.loads(row[0])
    assert classification["schema_version"] == "2.0.0"

    # 镜像值即排序依据：v2 评分 0 也排在旧版本高分候选之前
    res = review_atom(conn, "connector.location-v2", approved=True)
    assert res["status"] == "registered"
    _register(
        conn,
        _connector_atom(
            "connector.location-v1", compat=compat, schema_version="1.0.0"
        ),
        score=9.0,
    )
    results = connectors.match_connector(conn, "location", DEVICE)
    assert [c["atom_id"] for c in results] == [
        "connector.location-v2",
        "connector.location-v1",
    ]
    assert results[0]["schema_version"] == "2.0.0"
    assert results[1]["schema_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# 3. GET /connectors/match：形状 / 422 / 查询参数覆盖探测值
# ---------------------------------------------------------------------------


def _submit(client, atom):
    r = client.post("/atoms", json=atom, headers=_h(ADMIN_TOKEN))
    assert r.status_code == 201, r.text


def _review(client, atom_id, approved=True, comments=""):
    r = client.post(
        f"/atoms/{atom_id}/review",
        json={"approved": approved, "reviewer": "admin-reviewer", "comments": comments},
        headers=_h(ADMIN_TOKEN),
    )
    assert r.status_code == 200, r.text
    return r.json()


def _register_via_api(client, atom, score=None):
    _submit(client, atom)
    body = {"approved": True, "reviewer": "admin-reviewer"}
    if score is not None:
        body["score"] = score
    r = client.post(
        f"/atoms/{atom['atom_id']}/review", json=body, headers=_h(ADMIN_TOKEN)
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_match_endpoint_returns_device_function_candidates(client):
    """200 形状钉死：{device, function, candidates}；viewer 可读；
    候选含新增 schema_version 与 preferred 两键。"""
    _register_via_api(
        client,
        _connector_atom(
            "connector.location-ok",
            compat={"os": "android", "manufacturer": "samsung", "hardware": ["gps"]},
            schema_version="1.2.0",
            preferred=True,
        ),
        score=7.5,
    )
    r = client.get(
        "/connectors/match", params={"function": "location"}, headers=_h(VIEWER_TOKEN)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"device", "function", "candidates"}
    assert body["function"] == "location"
    assert set(body["device"]) == {"os", "os_version", "manufacturer", "hardware"}
    # fixture 已清空设备环境变量：探测值全部为 None/空
    assert body["device"] == {
        "os": None,
        "os_version": None,
        "manufacturer": None,
        "hardware": [],
    }
    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["atom_id"] == "connector.location-ok"
    assert set(candidate) == {
        "atom_id",
        "manufacturer_match",
        "score",
        "compatibility",
        "schema_version",
        "preferred",
    }
    assert candidate["schema_version"] == "1.2.0"
    assert candidate["preferred"] is True


def test_match_endpoint_missing_function_returns_422(client):
    """function 为必填查询参数，缺失由 FastAPI 返回 422。"""
    r = client.get("/connectors/match", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 422


def test_match_endpoint_query_params_override_detected_device(client, monkeypatch):
    """查询参数优先于环境变量探测值；未提供的字段保留探测值。"""
    monkeypatch.setenv(connectors.ENV_DEVICE_OS, "android")
    monkeypatch.setenv(connectors.ENV_DEVICE_OS_VERSION, "12")
    monkeypatch.setenv(connectors.ENV_DEVICE_MANUFACTURER, "samsung")
    monkeypatch.setenv(connectors.ENV_DEVICE_HARDWARE, "gps,camera")
    _register_via_api(
        client,
        _connector_atom(
            "connector.location-ok",
            compat={"os": "android", "manufacturer": "samsung", "hardware": ["gps"]},
        ),
        score=7.5,
    )

    # 基线：只传 function，device 全部来自环境变量探测，候选命中
    r = client.get(
        "/connectors/match", params={"function": "location"}, headers=_h(VIEWER_TOKEN)
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device"] == {
        "os": "android",
        "os_version": "12",
        "manufacturer": "samsung",
        "hardware": ["gps", "camera"],
    }
    assert [c["atom_id"] for c in body["candidates"]] == ["connector.location-ok"]

    # 覆盖 os/manufacturer：device 反映覆盖值，os_version 保留探测值；
    # 候选因 os 不符被硬过滤为空
    r = client.get(
        "/connectors/match",
        params={"function": "location", "os": "ios", "manufacturer": "xiaomi"},
        headers=_h(VIEWER_TOKEN),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device"] == {
        "os": "ios",
        "os_version": "12",  # 未提供 → 保留探测值
        "manufacturer": "xiaomi",
        "hardware": ["gps", "camera"],
    }
    assert body["candidates"] == []

    # 覆盖 hardware（逗号分隔）：候选因 gps 缺失被硬过滤为空
    r = client.get(
        "/connectors/match",
        params={"function": "location", "hardware": "bluetooth"},
        headers=_h(VIEWER_TOKEN),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["device"]["hardware"] == ["bluetooth"]
    assert body["candidates"] == []


# ---------------------------------------------------------------------------
# 4. implements 审核校验（review_atom 批准路径）
# ---------------------------------------------------------------------------

# 钉死的 location I/O 标准：{latitude:number, longitude:number, accuracy:number, timestamp:string}
LOCATION_SCHEMA_OUTPUT = {
    "type": "json",
    "properties": {
        "latitude": {"type": "number"},
        "longitude": {"type": "number"},
        "accuracy": {"type": "number"},
        "timestamp": {"type": "string"},
    },
}
LOCATION_IO = {
    "output": {
        "latitude": "number",
        "longitude": "number",
        "accuracy": "number",
        "timestamp": "string",
    }
}


def _register_location_schema(client):
    """注册 location 接口标准原子（architecture.type == "schema"）。"""
    atom = _connector_atom(
        "schema.location-v1", arch_type="schema", output_schema=LOCATION_SCHEMA_OUTPUT
    )
    _submit(client, atom)
    assert _review(client, "schema.location-v1")["status"] == "registered"


def _review_comments(client, atom_id):
    r = client.get(f"/atoms/{atom_id}", headers=_h(VIEWER_TOKEN))
    assert r.status_code == 200, r.text
    return r.json()["lifecycle"]["review_result"]["comments"]


def test_implements_unknown_schema_when_standard_not_registered(client):
    """implements 指向未注册的接口标准 → 强制拒绝，reason 以 implements_unknown_schema 开头。"""
    _submit(
        client,
        _connector_atom(
            "connector.location-ghost", implements="schema.location-v1", io=LOCATION_IO
        ),
    )
    assert _review(client, "connector.location-ghost")["status"] == "rejected"
    assert _review_comments(client, "connector.location-ghost").startswith(
        "implements_unknown_schema"
    )


def test_implements_unknown_schema_when_target_is_not_schema_atom(client):
    """implements 指向 architecture.type != schema 的普通原子 → implements_unknown_schema。"""
    _register_via_api(client, _connector_atom("connector.location-plain"))
    _submit(
        client,
        _connector_atom(
            "connector.location-misref",
            implements="connector.location-plain",
            io=LOCATION_IO,
        ),
    )
    assert _review(client, "connector.location-misref")["status"] == "rejected"
    assert _review_comments(client, "connector.location-misref").startswith(
        "implements_unknown_schema"
    )


def test_implements_mismatch_when_output_keys_missing(client):
    """声明输出缺标准定义的键 → implements_mismatch。"""
    _register_location_schema(client)
    _submit(
        client,
        _connector_atom(
            "connector.location-missing",
            implements="schema.location-v1",
            io={"output": {"latitude": "number", "longitude": "number"}},
        ),
    )
    assert _review(client, "connector.location-missing")["status"] == "rejected"
    assert _review_comments(client, "connector.location-missing").startswith(
        "implements_mismatch"
    )


def test_implements_mismatch_when_output_type_differs(client):
    """声明输出键齐但类型与标准不一致 → implements_mismatch。"""
    _register_location_schema(client)
    io = {"output": dict(LOCATION_IO["output"], latitude="string")}
    _submit(
        client,
        _connector_atom(
            "connector.location-wrongtype",
            implements="schema.location-v1",
            io=io,
        ),
    )
    assert _review(client, "connector.location-wrongtype")["status"] == "rejected"
    assert _review_comments(client, "connector.location-wrongtype").startswith(
        "implements_mismatch"
    )


def test_implements_exact_match_approves_normally(client):
    """声明输出完全覆盖标准且类型一致 → 正常 registered。"""
    _register_location_schema(client)
    _submit(
        client,
        _connector_atom(
            "connector.location-good",
            implements="schema.location-v1",
            io=LOCATION_IO,
        ),
    )
    assert _review(client, "connector.location-good")["status"] == "registered"


def test_atom_without_implements_unaffected_by_review(client):
    """未声明 implements 的普通原子零影响：正常批准，reviewer 评语不被覆写。"""
    _submit(client, _connector_atom("connector.location-noimpl"))
    assert (
        _review(client, "connector.location-noimpl", comments="常规通过")["status"]
        == "registered"
    )
    assert _review_comments(client, "connector.location-noimpl") == "常规通过"
