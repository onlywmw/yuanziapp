# 链备份方案 — 电脑 + GitHub

> **定位**: 电脑坏了 → git clone → 链完整恢复
> **原则**: GitHub 只是你的个人备份, 不是共识层

---

## 一、仓库

```
github.com/onlywmw/yuanzi-chain  (私有仓库)

目录:
  blocks/
    000000.json
    000001.json
    ...
  chain_state.json
```

## 二、自动备份

`chain.py` 的 `add_block()` 函数末尾加三行：

```python
def add_block(self, transactions):
    """打包交易 → 新块 → 写文件 → git push"""
    
    block = self._build_block(transactions)
    self._write_block_file(block)
    self._update_chain_state(block)
    
    # 自动备份到 GitHub
    self._backup_to_github(block.height)
    
    return block.hash


def _backup_to_github(self, height):
    """git add → commit → push (静默, 不阻塞)"""
    import subprocess
    
    repo = self.backup_repo  # "github.com/onlywmw/yuanzi-chain"
    
    subprocess.run(
        ["git", "add", "blocks/", "chain_state.json"],
        cwd=self.chain_dir, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", f"block #{height}"],
        cwd=self.chain_dir, capture_output=True
    )
    subprocess.run(
        ["git", "push", "origin", "main"],
        cwd=self.chain_dir, capture_output=True
    )
```

## 三、恢复

```
新电脑:

  git clone git@github.com:onlywmw/yuanzi-chain.git
  cd yuanzi-chain
  python chain.py verify --full      ← 验证整条链完整性

  验证通过 → 链恢复完成。
```

## 四、安全

```
GitHub 上的数据:
  每个人都能 clone (如果是公开仓库)
  但没人能改 — 改了任何一个字节, Merkle root 就对不上
  验证脚本一跑就知道有没有被篡改

所以:
  GitHub 不能"伪造"公证
  GitHub 只能"保存"公证
  备份的安全性 = 链本身的不可篡改性
```

---

> **2.5h 的链 + 3 行代码的备份 = 电脑和 GitHub 各一份。电脑坏了 → clone 回来 → 完整链。**
