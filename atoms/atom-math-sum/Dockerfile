# 使用极简的 Python 环境
FROM python:3.10-slim

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 暴露标准端口
EXPOSE 8080

# 启动标准服务
CMD ["python", "server.py"]
