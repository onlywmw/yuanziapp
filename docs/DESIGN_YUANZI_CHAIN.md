# Yuanzi Chain 设计

> **定位**: 只做一件事——原子公证。不是通用链, 不是代币, 不是智能合约平台。
> **目标**: 轻到能跑在 Android 上, 社区的每个人都能成为验证节点。

---

## 一、只做一件事

```
不是:
  ❌ 通用智能合约平台 (不需要)
  ❌ 加密货币 (不需要)
  ❌ DeFi/NFT (不需要)

只做:
  ✅ 原子注册公证 — 谁、在什么时候、创造了什么原子
  ✅ 所有权转让 — 谁把原子转给了谁
  ✅ 不可篡改 — 任何人包括我自己都改不了
```

## 二、数据长什么样

```
一个区块:

Block #142
  ┌─────────────────────────────────────┐
  │ prev_hash:  0x7a3b...              │  ← 链上前一个区块的哈希
  │ timestamp:   2026-07-19T15:30:00Z  │
  │ merkle_root: 0xf8d2...              │  ← 所有交易的 Merkle 树根
  │                                     │
  │ Transactions:                       │
  │  ┌──────────────────────────────┐  │
  │  │ type: notarize               │  │
  │  │ atom_id: com.zhangsan.music  │  │
  │  │ signature_hash: de5ed4...    │  │
  │  │ author: 张三                  │  │
  │  │ action: register             │  │
  │  └──────────────────────────────┘  │
  │  ┌──────────────────────────────┐  │
  │  │ type: transfer               │  │
  │  │ atom_id: com.lisi.tool       │  │
  │  │ from: 李四                    │  │
  │  │ to: 王五                      │  │
  │  └──────────────────────────────┘  │
  └─────────────────────────────────────┘

每个交易约 300 字节。
每个区块约 10-100 笔交易。
每个区块约 3-30 KB。
```

## 三、共识

```
PoS (Proof of Stake):

  成为验证者:
    抵押 Yuanzi Token (链上原生代币, 仅用于质押, 不流通)
    最少抵押: 100 YZT
    没有 YZT 的节点 → 轻节点 (只验证, 不出块)

  出块:
    每 10 秒一个区块
    验证者轮流提议区块
    其他验证者投票 (2/3 通过 → 区块确认)

  代币:
    YZT 只在链上使用:
      · 成为验证者要抵押
      · 作恶 (伪造公证) → 抵押被罚没
      · 不用于支付, 不用来炒

    初始分配:
      · 1000 万 YZT 给创始作者
      · 500 万 YZT 分发给早期注册者
      · 出块奖励: 每个块 1 YZT (逐年减半)
```

## 四、运行模式

```
全节点 (验证者):
  · 运行在服务器/高性能 Android 上
  · 抵押 YZT, 参与出块
  · 存储全部区块数据 (~1 GB/年)
  · 全球预计 10-100 个

轻节点 (普通用户):
  · 运行在手机上
  · 只存区块头 (~50 MB/年)
  · 验证原子公证时 → 向全节点请求 Merkle 证明
  · 不参与出块

超轻节点 (APK 内部):
  · 只存最近的区块头
  · 验证时 → 连到社区全节点
  · 几乎不占存储
```

## 五、验证流程

```
用户: "这个原子真的是张三创建的吗？"

  1. 从 atom.runtime.blockchain_tx 拿到交易哈希
  2. 向任意全节点请求 "交易 abc123 的 Merkle 证明"
  3. 全节点返回:
     · 交易内容
     · Merkle Path (从交易到 Merkle Root 的路径)
  4. 轻节点用自己存的区块头验证:
     · 交易哈希 → Merkle Path → Merkle Root ✓
     · Merkle Root 匹配区块头中的值 ✓
     · 区块头哈希链回溯到创世块 ✓
  5. 确认: 这笔公证确实在链上, 且未被篡改

  不需要信任全节点 — 全节点骗不了 Merkle 证明。
```

## 六、网络层

```
发现:
  · 启动时连接种子节点 (写死在代码里的 3-5 个长期运行的节点)
  · 种子节点返回当前在线验证者列表
  · 之后通过 P2P 发现新节点

通信:
  · gRPC 或 libp2p (轻量)
  · 端口: 26656 (默认, 可配置)
  · 协议: Protobuf 序列化

Android 适配:
  · Android 有后台限制 → 轻节点用按需连接, 不保持长连接
  · 验证时才连, 验证完断开
```

## 七、客户端

```
Yuanzi 链客户端:

  yuanzi-chain/
  ├── node/
  │   ├── chain.py          ← 链状态管理 (区块存储, 验证)
  │   ├── consensus.py      ← PoS 共识 (出块, 投票)
  │   ├── mempool.py        ← 交易池 (待打包的交易)
  │   ├── p2p.py            ← 网络层 (发现, 连接, 同步)
  │   ├── merkle.py         ← Merkle 树
  │   ├── validator.py      ← 验证者逻辑 (抵押, 出块, 罚没)
  │   └── light_client.py   ← 轻节点 (区块头同步, Merkle 验证)
  │
  ├── cli/
  │   └── yuanzi-chain      ← 命令行 (init, start, stake, verify)
  │
  └── config.py              ← 链参数 (出块时间, 抵押量, 奖励)
```

## 八、创世

```
创世块内容:

  {
    "chain_id": "yuanzi-mainnet",
    "genesis_time": "2026-08-01T00:00:00Z",
    "initial_validators": [
      {"address": "yuanzi1...", "name": "Yuanzi Foundation", "stake": 1000000}
    ],
    "initial_balances": {
      "yuanzi1...": 10000000,   ← 创始作者
      "yuanzi2...": 5000000     ← 早期贡献者池
    },
    "notarization": {
      "atom_id": "yuanzi.chain",
      "signature_hash": "genesis",
      "author": "Yuanzi",
      "action": "genesis",
      "description": "Yuanzi Chain — 原子公证专用链"
    }
  }

创世块的第一条公证: 链自己。
```

## 九、与现有系统的对接

```
agent.db
  atom_registry
    runtime_json.blockchain = {
      "network": "yuanzi-mainnet",
      "tx_hash": "abc123...",
      "block_height": 142,
      "confirmed_at": "2026-07-19T15:32:00Z"
    }

API 新增:
  POST /api/v1/notarize/{atom_id}       ← 将已注册原子公证上链
  GET  /api/v1/atoms/{id}/verify        ← 返回现 + Merkle 证明 (验证用)
  GET  /api/v1/chain/status             ← 链状态 (高度/验证者/出块时间)
```

## 十、渐进式去中心化

```
Phase 1: 单一验证者 (现在)
  · Yuanzi 官方运行一个验证者
  · 社区运行轻节点
  · 可以验证, 但不能出块

Phase 2: 邀请验证者 (几个月内)
  · 邀请 5-10 个活跃作者成为验证者
  · 抵押 YZT → 参与出块
  · 链从单一验证者 → 多点共识

Phase 3: 完全开放 (一年内)
  · 任何人都可以抵押 YZT 成为验证者
  · 全球 50-100 个验证者
  · 真正去中心化

Phase 4: 社区自治 (两年内)
  · 链参数由验证者投票决定
  · 创始团队只是普通验证者之一
  · 谁来也改不了——包括创始团队
```

## 十一、实施

```
阶段 1: 链核心 (1 周)
  · chain.py + consensus.py + merkle.py + p2p.py
  · 单一验证者模式
  · 能出块, 能验证

阶段 2: 轻节点 (3 天)
  · light_client.py
  · Android 集成

阶段 3: 多验证者 (1 周)
  · validator.py + stake 逻辑
  · 多点共识

总工作量: ~2.5 周。
```

---

> **不是通用链。只做一件事——原子公证。300 字节的交易, 10 秒一个块, 全球 100 个验证者。轻到能跑在手机上。**
