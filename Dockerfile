# 行情看板容器镜像：默认监听 0.0.0.0:8000
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STOCKMON_HOST=0.0.0.0 \
    STOCKMON_PORT=8000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# 数据卷：自选股与历史库放在容器外，便于持久化
VOLUME ["/app/data"]
ENV STOCKMON_DB_PATH=/app/data/quotes.db

CMD ["python", "app.py"]
