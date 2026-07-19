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
  自动 git push → GitHub 备份
       ↓
  任何人可以验证:
    拿 tx_hash → 查链 → Merkle 证明 → 确认未被篡改
```

## 二、什么原子上链

不是全部。只公证"值得公证"的：

```
✅ 上链:
  · 有 soul 的终端原子 (有叙事+风格 → 是作品)
  · 资产类原子 (author 标记为 asset)
  · 所有权转让时

❌ 不上链:
  · 基础原子 (system.* — 系统内置, 不需要证明)
  · 普通工具原子 (mcp.* — 管道, 不是作品)
  · 感知/融合/决策/执行原子
```

判断条件：`soul.narrative 非空 + soul.style 非空` 或 `category ∈ {asset, artwork, service}`

## 三、链的设计

```
Yuanzi Chain:
  结构:        区块链表, 每个区块一个 JSON 文件
  存储:        本地 C:\Users\Administrator\yuanzi_chain\blocks\
  备份:        出块自动 git push 到 GitHub
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
# registry.py: submit_atom() 末尾

if _should_notarize(atom):
    chain = get_chain()
    tx_hash = chain.add_block([{
        "type": "notarize",
        "atom_id": atom["atom_id"],
        "signature_hash": signature,
        "author": atom["ownership"]["author"],
        "action": "register",
    }])
    # 存回 runtime
    atom["runtime"]["blockchain"] = {
        "network": "yuanzi-chain",
        "tx_hash": tx_hash,
        "notarized_at": now_iso()
    }
```

上链失败 → 不阻塞注册。原子正常入库，runtime.blockchain 为空。

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
  ✅ yuanzi_chain/chain.py + merkle.py (200 行, 本地链核心)
  ✅ 创世块 + 测试块

待实施:
  ⬜ registry.py 加 _should_notarize + add_block 调用 (1h)
  ⬜ api.py 加 GET /atoms/{id}/verify (30min)
  ⬜ atom.runtime 加 blockchain 字段 (迁移 012)
  ⬜ yuanzi_chain/ 加 github backup 自动推送 (3 行代码)
```

## 九、文件清单

```
yuanzi_chain/                       ← 链代码
  chain.py, merkle.py, blocks/

mcp-yuanzi-bridge/
  registry.py                       ← + _should_notarize + add_block
  api.py                            ← + GET /verify
  migrations/012_blockchain.sql     ← + blockchain 字段

docs/
  DESIGN_ATOM_NOTARIZATION.md       ← 本文档
  DESIGN_YUANZI_CHAIN.md            ← 分布式方案
  DESIGN_YUANZI_CHAIN_LOCAL.md      ← 本地实施
  CHAIN_BACKUP_GITHUB.md            ← 备份方案
  CHAIN_ATOM_INTEGRATION.md         ← 集成细节
```

---

> **自己的链, 公证自己的原子。现在电脑上跑, 未来社区一起跑。谁也改不了——包括创造链的人。**
