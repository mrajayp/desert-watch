FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DW_DATA_DIR=/data DW_CONFIG_DIR=/app/config DW_FRONTEND_DIST=/app/frontend/dist \
    DW_SCHEDULER=1 DW_COOKIE_SECURE=1
WORKDIR /app/backend
COPY backend/pyproject.toml ./
RUN pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" "pyyaml>=6.0" "httpx>=0.27" \
    "feedparser>=6.0" "apscheduler>=3.10,<4" "networkx>=3.3" "scikit-learn>=1.5"
COPY backend/app ./app
COPY config /app/config
COPY --from=web /web/dist /app/frontend/dist
RUN useradd -m dw && mkdir -p /data && chown dw /data
USER dw
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
