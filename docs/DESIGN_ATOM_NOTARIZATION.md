# 原子公证系统设计

> **状态**: `📐 design-ready`
> **目标**: 资产类原子的不可篡改所有权证明
> **方案**: 自己创链, 本地运行, GitHub 备份, 未来分布式

---

## 一、做什么

```
注册一个资产原子时:

  原子的 SHA-256 签名 + 作者 + 时间戳
       ↓
  写入 Yuanzi Chain (自己的链, 本地)
       ↓
  返回 tx_hash → 存入 atom.runtime.blockchain
       ↓
  可选 git push → GitHub 备份 (默认关闭)
       ↓
  任何人可以验证:
    拿 tx_hash → 查链 → Merkle 证明 → 确认未被篡改
```

## 二、什么原子上链

不是全部。只公证"值得公证"的：

```
✅ 上链:
  · 资产类原子 (category ∈ {asset, artwork, service})
  · 有 soul 的终端原子 (有叙事+风格 → 是作品)
  · 所有权转让时

❌ 不上链:
  · 基础原子 (system.* — 系统内置, 不需要证明)
  · 普通工具原子 (mcp.* — 管道, 不是作品)
  · 感知/融合/决策/执行原子
```

判断条件（写死，与实现一致）：

`classification.category ∈ {asset, artwork, service}`，
或 soul 规则——`classification.narrative` 与 `classification.style` 均非空
（soul 字段位于 classification 扩展，见 DESIGN_ATOM_FOUNDATION_V2 §3）

## 三、链的设计

```
Yuanzi Chain:
  结构:        区块链表, 每个区块一个 JSON 文件
  存储:        仓库内 yuanzi_chain/blocks/ (YUANZI_CHAIN_HOME 可覆盖)
  备份:        git push 默认关闭; 仅当 YUANZI_CHAIN_REPO 指向独立 git 仓库时启用
               (绝不 push 主仓库)
  共识:        Phase 1 单节点 (现在) → Phase 4 社区分布式 (未来)
  验证:        Merkle 树 + prev_hash 链

每个区块:
  {
    height, prev_hash, timestamp, merkle_root,
    transactions: [{type, atom_id, signature_hash, author, action}]
  }

每笔交易: ~300 字节
每年数据: 假设 1000 个资产原子 = 300 KB
```

## 四、注册流程集成

```python
# registry/core.py: review_atom() 审核通过时

if _should_notarize(atom):
    chain = get_chain()
    tx = {
        "type": "notarize",
        "atom_id": atom["atom_id"],
        "signature_hash": signature,
        "author": atom["ownership"]["author"],
        "action": "register",
    }
    chain.add_block([tx])          # 返回块哈希（区块寻址用）
    tx_hash = hash_tx(tx)          # 交易哈希需调用方自算
    # 存回 runtime
    atom["runtime"]["blockchain"] = {
        "network": "yuanzi-chain",
        "tx_hash": tx_hash,
        "notarized_at": now_iso()
    }
```

上链失败 → 不阻塞审核结果。原子正常完成注册流程，runtime.blockchain 为空。

## 五、验证

```
GET /atoms/{id}/verify

  → 读取 atom.runtime.blockchain.tx_hash
  → chain.verify_atom(atom_id)
  → 返回:

  {
    "verified": true,
    "network": "yuanzi-chain",
    "tx_hash": "abc123...",
    "block_height": 142,
    "atom_id": "com.zhangsan.music",
    "author": "张三",
    "chain_integrity": true
  }

verified = true:
  · Merkle 证明通过 (交易确实在区块中)
  · 链完整性通过 (prev_hash 从头到尾一致)
  · 签名匹配 (链上的 signature_hash == 原子的 SHA-256)
```

## 六、备份与恢复

```
备份: 出块 → git add + commit + push → GitHub
      (默认关闭; 需 YUANZI_CHAIN_REPO 指向独立备份仓库, 见 §三)
恢复: git clone → chain.verify_full_chain() → 完整性确认 → 继续出块

GitHub 只是备份, 不是验证层。
链的安全性来自 Merkle 证明, 不是 GitHub。
```

## 七、未来分布式

```
Phase 1 (现在):    单节点本地 → GitHub 备份
Phase 2 (近期):    邀请验证者 → 多点共识
Phase 3 (中期):    PoS 开放 → 任何人可抵押出块
Phase 4 (远期):    社区自治 → 谁也改不了, 包括创始团队

每阶段 Schema 不变, API 不变。
只是共识层从 1 个节点变成 N 个节点。
```

## 八、实施

```
已完成:
  ✅ yuanzi_chain 包结构修复（__init__.py re-export，包相对导入，
     YUANZI_CHAIN_HOME 可覆盖数据目录，git push 备份默认关闭）
  ✅ YuanziChainProvider 接入 notarize.py，默认 network = "yuanzi-chain"，
     链不可用时回退 LocalLedgerProvider（network "local"）
  ✅ API 两条路由：GET /atoms/{id}/verify + POST /atoms/{id}/notarize
  ✅ 防重放（同 atom+action 不重复上链）与审计链（复用 registry 审计链）
  ✅ 公证数据零迁移落 atom.runtime_json；34 个测试全部通过
  ✅ Arweave 方案已废弃删除

待实施:
  ⬜ Phase 2+ 多点共识（见 §七）
```

## 九、文件清单

```
yuanzi_chain/                       ← 链代码（默认后端）
  __init__.py, chain.py, merkle.py, blocks/, chain_state.json

mcp-yuanzi-bridge/
  notarize.py                       ← 公证服务层（provider 抽象 + notarize/verify）
  registry/core.py                  ← review_atom 审核通过钩子 (_trigger_notarize_on_register)
  api.py                            ← GET /atoms/{id}/verify + POST /atoms/{id}/notarize
  tests/test_notarize.py            ← 公证核心测试 (21)
  tests/test_notarize_api.py        ← 公证 API 测试 (13)
  migrations/012_blockchain.sql     ← 未采用（零迁移方案，写入 runtime_json）

docs/
  DESIGN_ATOM_NOTARIZATION.md       ← 本文档（唯一权威）
```

---

> **自己的链, 公证自己的原子。现在电脑上跑, 未来社区一起跑。谁也改不了——包括创造链的人。**
