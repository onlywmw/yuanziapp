# 多维共振 — 实现方案

> **核心**: 5 类维度 × N 个原子 = 每对原子几十个交叉值。最强的几个决定集群。
> **计算量**: 12 原子 × 5 维度 × 66 对 = < 1ms

---

## 一、每个原子的场

```python
# 每个原子发出自己的维度值
# 不是固定字段, 每个原子不同

weather.field = {
    "物理": {"强度": 0.8, "密度": 0.9, "节奏": 0.6},
    "时间": {"持续": 2.0, "转折": 0.0},
    "情绪": {"能量": 0.3, "开放度": 0.2}
}

music.field = {
    "物理": {"密度": 0.9, "节奏": 0.5},
    "情绪": {"能量": 0.4, "开放度": 0.3, "熟悉度": 0.9}
}

calendar.field = {
    "时间": {"持续": 2.0, "转折": 0.0},
    "状态": {"专注度": 0.8}
}
```

## 二、共振计算

```python
def resonance(atom_a, atom_b):
    """两个原子之间的共振分数"""
    total = 0.0
    
    for category_a, dims_a in atom_a.field.items():
        for category_b, dims_b in atom_b.field.items():
            # 同类别共振 (物理×物理, 情绪×情绪)
            if category_a == category_b:
                weight = 2.0   # 同类别权重更高
            else:
                weight = 0.5   # 跨类别仍然算, 但权重低
            
            for name_a, val_a in dims_a.items():
                for name_b, val_b in dims_b.items():
                    # 加权乘积
                    w = atom_a.weights.get((name_a, name_b), 0.5)
                    total += w * weight * val_a * val_b
    
    return total
```

```
weather × music 的计算:
  
  同类别:
    物理: 强度(0.8)×密度(0.9) + 密度(0.9)×密度(0.9) + ...
    情绪: 能量(0.3)×能量(0.4) + 开放度(0.2)×开放度(0.3) + ...
    权重 ×2

  跨类别:
    物理.密度(0.9) × 情绪.能量(0.4)
    时间.持续(2.0) × 情绪.开放度(0.3)
    权重 ×0.5

  总计: 几十个交叉值加权求和 → 共振分数
```

## 三、权重学习

```python
# 初始: 所有权重 = 0.5 (中性)
# 每次用户接受一个集群输出 → 更新权重

def learn(atom_a, atom_b, user_accepted):
    """用户接受或忽略 → 调整权重"""
    
    if user_accepted:
        # 加强这次共振中贡献大的维度对
        for (name_a, name_b), contribution in top_contributions(atom_a, atom_b):
            atom_a.weights[(name_a, name_b)] += 0.05 * contribution
    else:
        # 减弱
        for (name_a, name_b), contribution in top_contributions(atom_a, atom_b):
            atom_a.weights[(name_a, name_b)] -= 0.03

# 30 天后:
# weather 知道: "我的'密度'和 music 的'密度'权重从 0.5 涨到了 0.9"
# weather 知道: "我的'强度'和 music 的'能量'权重从 0.5 降到了 0.2"
```

## 四、计算优化

```
只算活跃原子:  当前发出信号的原子 (12 个), 不是全部 61 个
缓存:          最近 10 秒内的共振结果复用
阈值:          初期全部算, 后期跳过历史上从未共振过的维度对

最坏情况: 12 × 5 × 12 × 5 = 3600 次乘法 → < 1ms
优化后:   只算活跃 + 高频维度 → < 0.3ms
```

## 五、和现有系统的关系

```
每个原子加一个 field 属性, gravity.field(state) → dict
再加一个 weights 字典, 初始 0.5

handler 不变。
resonance 是独立函数, 不侵入 atom 内部。

Chaquopy 内嵌 → Python 算 → 全在本地。
```
