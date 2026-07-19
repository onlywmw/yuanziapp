# 区块链公证方案

> **定位**: 资产类原子的不可篡改时间戳 + 所有权证明
> **原则**: 轻量——不上合约, 不搞代币, 不要求钱包。就是一个公证处。

---

## 一、做什么

```
注册一个资产类原子时:

  原子的 SHA-256 签名 + 作者 + 时间戳
       ↓
  打包为一个 JSON
       ↓
  写入区块链 (一条纯数据交易)
       ↓
  返回交易哈希 → 存入 atom.runtime.blockchain_tx
       ↓
  任何人拿这个 tx hash 可以在链上查到原始数据
       ↓
  证明: "这个原子, 确实是张三在 2026-07-19 创建的, 没人能改"
```

## 二、什么时候触发

```
不是所有原子都上链。只在以下时机:

  1. 资产类原子首次注册 → 自动上链 (可选, 作者可跳过)
  2. 所有权转让 → 记录新交易 (谁→谁, 什么时候)
  3. 重大版本升级 → 记录新版本 (v1→v2, 链上可追溯)
  4. 原子下架/删除 → 记录终结 (原子生命周期结束)

普通工具原子不上链。感知原子不上链。
只有作者勾选了"这是资产"的注册原子才上链。
```

## 三、用什么链

```
方案 A: Arweave (推荐)
  费用: 一次性 ~$0.01 (永久存储)
  速度: 确认 ~5-10 分钟 (异步, 不阻塞注册)
  特点: 数据永久存在, 不需要持续付费

方案 B: Ethereum 数据字段 (calldata)
  费用: ~$0.05-0.50 (看 gas)
  速度: 确认 ~15 秒
  特点: 生态最大, 验证方便

方案 C: Solana 备注字段
  费用: ~$0.0001
  速度: 确认 < 1 秒
  特点: 极便宜, 快

推荐: Arweave (永久 + 便宜 + 异步不阻塞)
```

## 四、存什么

```json
{
  "version": 1,
  "atom_id": "com.zhangsan.premium-music",
  "signature_hash": "de5ed413bd72...",
  "author": "张三",
  "timestamp": "2026-07-19T15:30:00Z",
  "action": "register",
  "metadata_uri": "https://yuanzi.app/atoms/com.zhangsan.premium-music"
}
```

约 300 字节。Arweave 上 ~$0.005。

## 五、链上→本地

```
注册流程:

  1. submit_atom() → 写入 agent.db, 状态=submitted
  2. review_atom()  → 审核通过, 状态=registered
  3. 如果 atom.classification.category = "asset":
       → notarize_on_chain(atom)
       → 异步等待 tx hash
       → 存入 atom.runtime.blockchain_tx
       → 存入 atom.runtime.blockchain_network
  4. 正常返回注册成功 (不等待链确认)

  注册不阻塞——链上确认是异步的。
  用户看到 "已注册 + 链上公证中..." → 确认后 "链上公证完成 ✓"
```

## 六、验证

```
任何人可以验证:

  1. 从 atom.runtime.blockchain_tx 获取交易哈希
  2. 用链上浏览器或轻节点查询该交易
  3. 比对链上数据中的 signature_hash 和原子的 SHA-256 签名
  4. 一致 → 证明原子注册信息自那一刻起未被篡改

验证接口:
  GET /atoms/{id}/verify
  → {
      "verified": true,
      "blockchain": "arweave",
      "tx_hash": "abc123...",
      "confirmed_at": "2026-07-19T15:32:00Z",
      "data_matches": true
    }
```

## 七、Schema 扩展

`runtime_json` 新增:

```json
{
  "runtime": {
    "blockchain": {
      "network": "arweave",
      "tx_hash": "abc123...",
      "notarized_at": "2026-07-19T15:32:00Z",
      "verified": true
    }
  }
}
```

## 八、费用

```
谁付费？

  方案 A: 系统付 (Yuanzi 维护一个 Arweave 钱包)
    → 作者零费用, 系统承担小额永久存储成本
    → 适合: 鼓励作者标注资产, 不增加门槛

  方案 B: 作者付 (注册时可选, 不想上链就跳过)
    → 作者有自己的钱包, 自己付 gas
    → 适合: 作者对自己的资产有完全控制权

推荐 A+B: 默认系统付, 作者也可用自己的钱包。
```

## 九、实施

```
Phase 1: Arweave 集成 (2h)
  · 依赖: arweave-python-client (纯 Python, Chaquopy 兼容)
  · 钱包: 生成一个 Yuanzi 官方钱包 (环境变量存私钥)
  · 写入: 原子的 JSON → Arweave 交易
  · 查询: tx hash → 链上数据

Phase 2: 注册流程接入 (1h)
  · submit_atom 后判断 category == "asset"
  · 异步调用 notarize
  · 存储 tx hash

Phase 3: 验证接口 (30min)
  · GET /atoms/{id}/verify
  · 链上比对

总: ~4h。纯 Python, 零 APK 改动。
```

## 十、安全

```
私钥保护:
  系统钱包私钥 → 环境变量, 不写代码, 不进 git
  作者钱包私钥 → 作者自己管理, 系统不触碰

防重放:
  同一原子不重复上链 (检查 runtime.blockchain_tx 是否已存在)
  所有权转让产生新交易, 不是覆盖旧交易
```

---

> **不是 Web3 炒作。是公证处——证明"这个原子是张三在这个时间创建的"。轻到只有 300 字节的 JSON 上链。**
