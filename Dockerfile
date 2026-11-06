# 单镜像双用途：默认起 API 服务；前端在 docker-compose 里覆盖 command
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先只拷依赖清单：以后改代码不会让这一层缓存失效，重建快很多
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY app ./app
COPY scripts ./scripts
COPY data/raw ./data/raw

# 运行时会被 volume 覆盖；这里先建好，保证镜像单独跑也不会报错
RUN mkdir -p data/chroma data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
