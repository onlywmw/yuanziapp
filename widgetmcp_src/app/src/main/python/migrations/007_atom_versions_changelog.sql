-- 007_atom_versions_changelog: 版本快照增加 changelog 列（接口契约 1.6）。

ALTER TABLE atom_versions ADD COLUMN changelog TEXT;
