# ---- frontend build ----------------------------------------------------------
FROM node:22-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
# vite.config.ts writes to ../backend/static → /build/backend/static
RUN npm run build

# ---- runtime -----------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # fastembed caches ONNX weights here; baked into the image so the first
    # cycle after a deploy does not spend a minute downloading them.
    HF_HOME=/app/.cache/huggingface \
    DATA_DIR=/data

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" greenlet asyncpg \
      alembic pgvector pydantic pydantic-settings httpx feedparser "selectolax<1.0" pyyaml anthropic \
      fastembed numpy apscheduler itsdangerous python-dateutil pypdf

COPY backend/ ./
COPY data/ /data/
COPY --from=frontend /build/backend/static ./static

# Warm the embedding model into the image layer rather than the first request.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"

EXPOSE 8000
# Migrations + source load run in scripts/start.sh before uvicorn (idempotent).
# sh -c so ${PORT} expands — Railway injects it at runtime.
CMD ["sh", "scripts/start.sh"]
