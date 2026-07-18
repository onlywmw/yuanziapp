# 基础原子标准

> 先把一块砖烧到完美，再谈盖楼。

## 1. 什么是基础原子

基础原子是系统中最小的可执行单元，具备以下特性：

- **极简**：只做一件事
- **标准**：所有原子的目录结构、接口、行为完全一致
- **无状态**：不保存会话，只处理输入数据
- **可测试**：给定输入，必有确定输出

## 2. 标准目录结构

每个原子必须长成这样：

```
atom-<name>/
├── Dockerfile          # 标准构建（固定）
├── requirements.txt    # 依赖管理
├── server.py           # 标准外壳（固定，处理网络/Meta）
└── core.py             # 核心逻辑（唯一需要变的地方）
```

## 3. 标准接口

所有原子启动后必须暴露三个端点：

| 端点 | 方法 | 作用 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/meta` | GET | 自描述元数据（ID、名称、类型、Schema） |
| `/run` | POST | 执行入口，调用 `core.handler(data)` |

## 4. 开发新原子的步骤

1. 复制 `atom-template/`
2. 修改 `core.py` 中的 `handler(data)`
3. 修改 `server.py` 中 `/meta` 返回的身份证信息
4. （可选）修改 `requirements.txt` 添加依赖
5. 测试：`python server.py`，然后访问 `/health`、`/meta`、`/run`
6. 构建：`docker build -t atom-<name>:v1 .`

## 5. 已验证的原子

- `atom-math-sum`：计算两个数字的和，已本地验证通过

## 6. 输出格式约定

`core.handler` 必须返回以下两种结构之一：

成功：
```json
{
  "status": "success",
  "data": { ... }
}
```

失败：
```json
{
  "status": "error",
  "message": "错误说明"
}
```
