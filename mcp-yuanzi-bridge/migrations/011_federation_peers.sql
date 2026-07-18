-- 011_federation_peers: 联邦注册中心对等节点（M7 任务 7.4）。
-- trust_level: trusted（自动可见+评分同步）/ review（需审核）/ unknown（不共享）。

CREATE TABLE IF NOT EXISTS federation_peers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    base_url TEXT UNIQUE NOT NULL,
    trust_level TEXT NOT NULL DEFAULT 'review',
    added_at TEXT NOT NULL,
    last_synced_at TEXT
);
