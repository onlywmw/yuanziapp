# 图查询

> **做什么**: 用图语法查询原子关系，不用写 SQL
> **怎么做**: 简单的图查询语法 → 翻译为 SQLite 递归查询
> **原则**: 不引入图数据库，复用现有 SQLite

---

## 一、查询语法

```
MATCH (a:atom) WHERE a.category = "Database" RETURN a

MATCH (a:atom)-[r:depends_on]->(b:atom) RETURN a, r, b

MATCH (a:atom)-[:depends_on*1..3]->(b) WHERE a.atom_id = "mcp.postgres" RETURN b

MATCH (a:atom) WHERE a.rating >= 4 AND a.soul.style CONTAINS "reliable" RETURN a
```

## 二、支持的查询模式

```
1. 节点查询
   MATCH (a:atom) WHERE ... RETURN a
   → SELECT * FROM atom_registry WHERE ...

2. 路径查询 (直接依赖)
   MATCH (a)-[r:depends_on]->(b) WHERE ... RETURN a, b
   → 查 architecture.dependencies 字段

3. 路径查询 (多跳)
   MATCH (a)-[:depends_on*2..3]->(b) RETURN b
   → 递归 CTE, 深度 2-3 层

4. 聚合查询
   MATCH (a:atom) RETURN a.category, COUNT(*) as count
   → GROUP BY

5. 路径查找
   FIND PATH FROM "mcp.postgres" TO "system.file-read"
   → 最短路径, BFS
```

## 三、API

```
POST /api/v1/query
{
  "query": "MATCH (a:atom)-[:depends_on]->(b:atom) WHERE a.atom_id = 'mcp.postgres' RETURN b"
}

返回:
{
  "results": [
    {"b": {"atom_id": "system.http-get", "name": "HTTP GET", ...}}
  ],
  "translated_sql": "WITH RECURSIVE ...",
  "took_ms": 3
}
```

## 四、实现

```
查询 → 解析器 (手写小 parser) → AST → SQL 生成器 → SQLite

支持的模式:
  MATCH (变量:标签)           → FROM atom_registry
  -[:depends_on]->            → JOIN on dependencies
  -[:depends_on*N..M]->       → RECURSIVE CTE
  WHERE 条件                   → WHERE clause
  RETURN 字段                  → SELECT
  COUNT/AVG/MIN/MAX            → 聚合函数
  FIND PATH                    → BFS in Python
```

## 五、在何处使用

```
API:                 POST /api/v1/query (开发者用)
图谱参数面板:         输入查询 → 高亮匹配节点
工作流依赖分析:       自动查询 "这个原子被哪些工作流依赖"
市场推荐:             "和你喜欢的原子风格相似的原子"
```

## 六、实施

```
1h: 语法解析器 (match/where/return/find-path)
1h: SQL 生成器 (CTE/join/group/aggregate)
30min: API 端点
30min: 测试
```

---

> **不是 Neo4j。是 SQLite + 递归 CTE + 一层简单的图语法壳。**
