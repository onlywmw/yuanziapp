# core.py — connector.storage-android 存储连接器（连接原子 / connector atom）
"""枚举 Android 设备文件，输出统一 storage I/O 标准（implements: schema.storage-v1）。

输出契约（四个 I/O 接口标准之一，写死，见 docs/DESIGN_CONNECTOR_ATOM.md §四）：
    {"files": [{"name": str, "path": str, "size": number}]}
path 语义 = 可重新打开的文件引用（Android 10+ Scoped Storage 下统一为
content URI 字符串，而非真实文件系统路径）。

运行模式：
  1. mock 模式：环境变量 YUANZI_CONNECTOR_MOCK=1 时返回逼真的假数据，
     供桌面开发 / CI 测试使用，不触碰任何真实设备 API。
  2. 真实模式：仅在 Android 上可用（Chaquopy / Termux），经 SAF 或
     MediaStore 查询文件；非 Android 环境一律返回
     {"status": "error", "error": {"code": "unsupported_platform", ...}}。
"""
from __future__ import annotations

import os
import sys

MOCK_ENV = "YUANZI_CONNECTOR_MOCK"

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 10_000

# 逼真的 mock 数据：覆盖三种典型 path 形态——SAF document URI、SAF tree 下
# 的文档、应用私有目录文件；均为（名称, 引用, 字节数），符合 storage I/O 标准。
_MOCK_FILES = [
    {
        "name": "IMG_20240618_093012.jpg",
        "path": "content://com.android.providers.media.documents/document/image%3A1000000341",
        "size": 3_485_218,
    },
    {
        "name": "会议纪要-2024-06-17.pdf",
        "path": "content://com.android.externalstorage.documents/tree/primary%3ADocuments/document/primary%3ADocuments%2F%E4%BC%9A%E8%AE%AE%E7%BA%AA%E8%A6%81-2024-06-17.pdf",
        "size": 248_960,
    },
    {
        "name": "yuanzi_backup_20240601.zip",
        "path": "content://com.android.externalstorage.documents/tree/primary%3ADownload/document/primary%3ADownload%2Fyuanzi_backup_20240601.zip",
        "size": 18_874_368,
    },
    {
        "name": "voice_memo_0612.m4a",
        "path": "content://com.android.providers.media.documents/document/audio%3A1000000877",
        "size": 964_512,
    },
    {
        "name": "notes.txt",
        "path": "/storage/emulated/0/Android/data/app.yuanzi/files/notes.txt",
        "size": 1_204,
    },
]


def _mock_enabled() -> bool:
    return os.environ.get(MOCK_ENV) == "1"


def _is_android() -> bool:
    """尽力检测 Android 运行时。

    Chaquopy / Android 版 CPython 注入 sys.getandroidapilevel；
    Termux、Pydroid 等环境则暴露 ANDROID_ROOT + ANDROID_DATA 环境变量。
    """
    if hasattr(sys, "getandroidapilevel"):
        return True
    return "ANDROID_ROOT" in os.environ and "ANDROID_DATA" in os.environ


def _error(code: str, message: str) -> dict:
    return {"status": "error", "error": {"code": code, "message": message}}


def _limit(data: dict) -> int:
    try:
        n = int(data.get("limit", _DEFAULT_LIMIT))
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT
    return max(0, min(n, _MAX_LIMIT))


def _list_files_mock(data: dict) -> list:
    """mock 模式：返回符合 storage I/O 标准的假文件条目。"""
    return [dict(f) for f in _MOCK_FILES[: _limit(data)]]


def _list_files_real(data: dict) -> dict:
    """真实 Android 路径：经 Chaquopy 桥接 SAF / MediaStore 枚举文件。

    Storage Access Framework 桥接思路（App 层 + 本原子两步协作）：

      1. 授权（App 层，一次性）：发送 Intent(ACTION_OPEN_DOCUMENT_TREE)
         请用户选择目录，回调拿到 tree URI 后调用
         ContentResolver.takePersistableUriPermission() 固化读权限，
         再把 tree URI 作为 /run 入参 {"tree_uri": "..."} 传给本原子。
         Android 10+ Scoped Storage 下，这是访问共享存储的正规通路，
         无需任何存储权限。

      2. 查询（本原子）：Python 经 Chaquopy `from java import jclass` 拿到
         android.provider.DocumentsContract，用 tree URI 构造 children
         document URI，ContentResolver.query() 读取 COLUMN_DISPLAY_NAME /
         COLUMN_DOCUMENT_ID / COLUMN_SIZE 三列，映射为接口标准条目
         {"name", "path", "size"}（path = document URI 字符串，App 层可
         直接用它再次打开文件）。单层枚举；递归遍历由上层按需驱动。

      降级路径：未提供 tree_uri 时查询 MediaStore.Files 公共集合（需
      READ_EXTERNAL_STORAGE，Android 13+ 拆分为 READ_MEDIA_* 权限），
      用 ContentUris.withAppendedId 还原 content URI 作为 path——
      Android 10+ 不再暴露真实文件路径（_data 列不可靠），统一以
      content URI 充当可重新打开的引用。仍只输出 name/path/size 三字段，
      保证 implements 契约不变。
    """
    try:
        from java import jclass  # Chaquopy 桥：仅 Android 运行时存在
    except Exception:
        return _error(
            "android_bridge_unavailable",
            "java bridge unavailable: not running under Chaquopy/Android",
        )
    try:
        limit = _limit(data)
        tree_uri = data.get("tree_uri")
        python = jclass("com.chaquo.python.Python")
        context = python.getPlatform().getApplication()
        resolver = context.getContentResolver()
        files = []

        if tree_uri:
            # SAF：已授权目录树的直接子文档
            android_uri = jclass("android.net.Uri")
            documents = jclass("android.provider.DocumentsContract")
            tree = android_uri.parse(tree_uri)
            children = documents.buildChildDocumentsUriUsingTree(
                tree, documents.getTreeDocumentId(tree)
            )
            doc = jclass("android.provider.DocumentsContract$Document")
            projection = [
                doc.COLUMN_DISPLAY_NAME,
                doc.COLUMN_DOCUMENT_ID,
                doc.COLUMN_SIZE,
            ]
            cursor = resolver.query(children, projection, None, None, None)
            try:
                while cursor.moveToNext() and len(files) < limit:
                    doc_uri = documents.buildDocumentUriUsingTree(
                        tree, cursor.getString(1)
                    )
                    files.append(
                        {
                            "name": cursor.getString(0),
                            "path": doc_uri.toString(),
                            "size": int(cursor.getLong(2)),
                        }
                    )
            finally:
                cursor.close()
        else:
            # 降级：MediaStore.Files 公共集合，path 用 content URI 还原
            media = jclass("android.provider.MediaStore$Files")
            file_cols = jclass("android.provider.MediaStore$Files$FileColumns")
            content_uris = jclass("android.content.ContentUris")
            uri = media.getContentUri("external")
            projection = [file_cols.DISPLAY_NAME, file_cols._ID, file_cols.SIZE]
            cursor = resolver.query(
                uri, projection, None, None, file_cols.SIZE + " DESC"
            )
            try:
                while cursor.moveToNext() and len(files) < limit:
                    files.append(
                        {
                            "name": cursor.getString(0),
                            "path": content_uris.withAppendedId(
                                uri, cursor.getLong(1)
                            ).toString(),
                            "size": int(cursor.getLong(2)),
                        }
                    )
            finally:
                cursor.close()

        return {"status": "success", "data": {"files": files}}
    except Exception as exc:  # 任何 Java 桥异常都不能让原子崩溃
        return _error("storage_query_failed", f"{type(exc).__name__}: {exc}")


def handler(data: dict) -> dict:
    """连接原子入口。

    :param data: {"tree_uri": str (可选, SAF 授权后的目录树 URI),
                  "limit": int (可选, 默认 100, 上限 10000)}
    :return: {"status": "success", "data": {"files": [...]}} 或
             {"status": "error", "error": {"code": ..., "message": ...}}
    """
    data = data or {}
    if _mock_enabled():
        return {"status": "success", "data": {"files": _list_files_mock(data)}}
    if not _is_android():
        return _error(
            "unsupported_platform",
            "connector.storage-android requires Android "
            "(Chaquopy/Termux); set YUANZI_CONNECTOR_MOCK=1 for development",
        )
    return _list_files_real(data)
