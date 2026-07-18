-- 012_atoms_view_coalesce: atoms VIEW 加 COALESCE 防御层（ISOLATION_HARDENING_PLAN 加固3）。
-- JSON 字段缺失时返回 'unknown'/'' 而不是 NULL，APK GraphView 不再崩溃。

DROP VIEW IF EXISTS atoms;

CREATE VIEW atoms AS
SELECT
    r.id AS id,
    r.atom_id AS atom_id,
    COALESCE(r.name, 'unknown') AS label,
    COALESCE(json_extract(r.architecture_json, '$.type'), 'unknown') AS atom_type,
    COALESCE(json_extract(r.runtime_json, '$.endpoint'), '') AS endpoint,
    COALESCE(json_extract(r.lifecycle_json, '$.status'), 'unknown') AS status,
    COALESCE(
        (
            SELECT json_group_array(
                       'mcp/' || r.atom_id || '/' || COALESCE(json_extract(f.value, '$.name'), 'unknown')
                   )
            FROM json_each(json_extract(r.purpose_json, '$.functions')) AS f
            WHERE json_extract(f.value, '$.name') IS NOT NULL
        ),
        '[]'
    ) AS capabilities,
    COALESCE(json_extract(r.lifecycle_json, '$.updated_at'), r.updated_at, '') AS updated_at,
    COALESCE(json_extract(r.lifecycle_json, '$.created_at'), r.created_at, '') AS created_at
FROM atom_registry r;
