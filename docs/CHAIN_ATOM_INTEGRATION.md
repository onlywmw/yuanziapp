# 原子上链集成方案

> **定位**: 链和注册中心之间的桥 — 什么时候上链、怎么存、怎么验证
> **原则**: 只在注册时触发, 异步不阻塞, 存 tx_hash 即可

---

## 一、触发时机

```
submit_atom() 成功返回后, 判断:

  if atom.visibility == "terminal" and atom.soul 不为空:
    → 这个原子有作者、有灵魂、是作品
    → 值得公证

  if atom.classification.category in ["asset", "artwork", "service"]:
    → 作者标记为资产类
    → 必须公证

  else:
    → 普通工具原子, 不需要上链
```

不是所有原子上链。只有**有作者有灵魂的终端原子**才公证。

---

## 二、registry.py 改动

```python
# registry.py: submit_atom() 末尾加一段

from yuanzi_chain.chain import get_chain

def submit_atom(conn, atom, actor="system"):
    result = _insert_or_update(conn, atom, signature, actor)
    
    if result.get("success") and _should_notarize(atom):
        chain = get_chain()
        tx = {
            "type": "notarize",
            "atom_id": atom["atom_id"],
            "signature_hash": signature,
            "author": atom.get("ownership", {}).get("author", ""),
            "action": "register",
        }
        try:
            tx_hash = chain.add_block([tx])
            # 存回 runtime
            _update_runtime(conn, atom["atom_id"], {
                "blockchain": {"network": "yuanzi-chain", "tx_hash": tx_hash}
            })
        except Exception:
            pass  # 上链失败不阻塞注册
    
    return result


def _should_notarize(atom):
    """判断这个原子是否需要上链公证"""
    soul = atom.get("classification", {}).get("soul", {})
    category = atom.get("classification", {}).get("category", "")
    
    # 有灵魂的终端原子 → 上链
    if soul.get("narrative") and soul.get("style"):
        return True
    
    # 资产/作品/服务类 → 上链
    if category in ("asset", "artwork", "service"):
        return True
    
    return False
```

## 三、API 验证

```
GET /atoms/{id}/verify

  → 从 atom.runtime.blockchain.tx_hash 拿到交易哈希
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

  verified = true → 这个原子确实在链上, 且区块链完整无损
```

## 四、数据流

```
注册原子
    │
    ▼
submit_atom() → agent.db (正常流程)
    │
    ▼
_should_notarize() ? 
    │
    ├─ No  → 结束 (普通工具原子)
    │
    └─ Yes → chain.add_block([tx])
                  │
                  ▼
              区块写入 blocks/000XXX.json
                  │
                  ▼
              tx_hash 存入 atom.runtime.blockchain
                  │
                  ▼
              git push (备份到 GitHub)
```

## 五、atom.runtime 新增字段

```json
{
  "runtime": {
    "endpoint": "http://...",
    "blockchain": {
      "network": "yuanzi-chain",
      "tx_hash": "ed629a7d0110eea23338f6f302ead0316a71bedf77d0ce1486dcb326a008a0aa",
      "block_height": 1,
      "notarized_at": "2026-07-19T15:30:00Z"
    }
  }
}
```

## 六、实施

```
1h:  yuanzi_chain/ → 加到 Python path (或 pip install -e)
30m: registry.py 加 _should_notarize + add_block 调用
30m: api.py 加 GET /atoms/{id}/verify
30m: 测试
```

---

> **不是全量上链。只有有作者有灵魂的终端原子才公证。轻量、异步、不阻塞注册。**
