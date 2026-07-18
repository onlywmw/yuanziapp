-- 002_atoms_view: 旧 atoms 表改为 atom_registry 的只读 VIEW。
-- 解决 Critical Issue #4：双表双写漂移。列名与旧 atoms 表保持一致，
-- Widget MCP /graph 无需改动。
-- 注意：旧库中 atoms 是 TABLE，DROP VIEW IF EXISTS 遇到表会报错，
-- 所以这里只 DROP TABLE；迁移系统保证本文件只执行一次。

DROP TABLE IF EXISTS atoms;

CREATE VIEW atoms AS
SELECT
    r.id AS id,
    r.atom_id AS atom_id,
    r.name AS label,
    json_extract(r.architecture_json, '$.type') AS atom_type,
    json_extract(r.runtime_json, '$.endpoint') AS endpoint,
    json_extract(r.lifecycle_json, '$.status') AS status,
    COALESCE(
        (
            SELECT json_group_array(
                       'mcp/' || r.atom_id || '/' || json_extract(f.value, '$.name')
                   )
            FROM json_each(json_extract(r.purpose_json, '$.functions')) AS f
            WHERE json_extract(f.value, '$.name') IS NOT NULL
        ),
        '[]'
    ) AS capabilities,
    COALESCE(json_extract(r.lifecycle_json, '$.updated_at'), r.updated_at) AS updated_at,
    COALESCE(json_extract(r.lifecycle_json, '$.created_at'), r.created_at) AS created_at
FROM atom_registry r;
