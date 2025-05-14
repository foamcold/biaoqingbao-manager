# 使用官方 Python 运行时作为父镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 防止 Python 生成 .pyc 文件并将其写入磁盘
ENV PYTHONDONTWRITEBYTECODE 1
# 确保 Python 输出是无缓冲的，这在 Docker 日志中很有用
ENV PYTHONUNBUFFERED 1

# 安装系统依赖（如果需要，例如用于 Pillow 或其他 C 扩展）
# Build dependencies were here, removed as gevent is removed.

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码到工作目录
COPY . .

# 暴露 Gunicorn 将运行的端口
EXPOSE 5000

# 使用 Gunicorn 运行应用
# 注意：确保 app:app 中的 "app" 与你的 Flask 应用实例变量名以及文件名匹配
# 如果你的主文件是 main.py 并且 Flask 实例是 my_flask_app，则应为 main:my_flask_app
CMD ["gunicorn", "--workers", "1", "--timeout", "660", "--bind", "0.0.0.0:5000", "app:app"]