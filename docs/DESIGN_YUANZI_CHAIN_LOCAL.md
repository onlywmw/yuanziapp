# Yuanzi Chain — 本地单节点实施方案

> **阶段**: Phase 1 — 本地区块链, 未来分布式
> **原则**: 只做链, 不做网络。先让链在本地跑起来。

---

## 一、存哪

```
C:\Users\Administrator\yuanzi-chain\
├── blocks/
│   ├── 000000.json       ← 创世块
│   ├── 000001.json       ← 每个区块一个 JSON 文件
│   └── ...
├── chain_state.json      ← 当前高度、最新区块哈希
└── mempool.json          ← 待打包的交易
```

---

## 二、区块结构

```json
{
  "height": 142,
  "prev_hash": "0x7a3b...",
  "timestamp": "2026-07-19T15:30:00Z",
  "merkle_root": "0xf8d2...",
  "transactions": [
    {
      "type": "notarize",
      "atom_id": "com.zhangsan.music",
      "signature_hash": "de5ed4...",
      "author": "b'张三'",
      "action": "register"
    }
  ]
}
```

## 三、核心 API

```python
# yuanzi_chain/chain.py

class YuanziChain:
    def genesis(self):
        """创建创世块"""

    def add_block(self, transactions):
        """打包交易 → 新块 → 写文件 → 返回区块哈希"""

    def verify_atom(self, atom_id):
        """查链上有没有这个原子的公证, 返回证明"""

    def get_block(self, height):
        """按高度读区块"""

    def get_tx(self, tx_hash):
        """按交易哈希查交易"""
```

## 四、工作机制

```
注册一个资产原子时:

  registry.py: submit_atom("com.zhangsan.music")
       │
       ▼
  写入 agent.db (正常流程)
       │
       ▼
  判断 classification.category == "asset"
       │
       ▼
  调用 chain.add_block([{
    type: "notarize",
    atom_id: "com.zhangsan.music",
    signature_hash: atom.signature_hash,
    author: atom.ownership.author,
    action: "register"
  }])
       │
       ▼
  返回 tx_hash → 存入 atom.runtime.blockchain_tx
```

## 五、验证

```
GET /atoms/com.zhangsan.music/verify

  → 从 atom.runtime.blockchain_tx 拿到 tx_hash
  → chain.get_tx(tx_hash) 查到交易
  → 比对 signature_hash
  → 追溯 prev_hash 链到创世块
  → 确认没有篡改

返回:
  {
    "verified": true,
    "block_height": 142,
    "tx_hash": "abc123...",
    "chain_head": "0xf8d2...",
    "verified_blocks": 142
  }
```

## 六、文件清单

```
yuanzi-chain/
├── chain.py          ← 链核心 (~200行)
├── merkle.py         ← Merkle 树 (~80行)
├── cli.py            ← 命令行工具 (~50行)
└── blocks/           ← 区块数据目录

mcp-yuanzi-bridge/
└── registry.py       ← submit_atom 中加一行: chain.add_block(...)
```

## 七、实施

```
1h:  chain.py  + merkle.py
30m: 注册流程接入
30m: 验证接口
30m: 测试

2.5h 总工作量
```

---

> **Phase 1: 链在本地。Phase 4: 链在世界。代码不变, 只加网络层。**
