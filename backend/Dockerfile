# Build with: docker build -f backend/Dockerfile -t beans-backend .
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /build

RUN python -m venv "${VIRTUAL_ENV}"

COPY requirements.txt ./requirements.txt
COPY backend/requirements.txt ./backend-requirements.txt

RUN pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt -r backend-requirements.txt


FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8000 \
    UVICORN_WORKERS=1

RUN groupadd --system app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY backend /app/backend
COPY agents /app/agents
COPY database.py /app/database.py
COPY database_pg.py /app/database_pg.py
COPY database_config.py /app/database_config.py
COPY graph.py /app/graph.py
COPY llm.py /app/llm.py
COPY tenant_manager.py /app/tenant_manager.py
COPY backend/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN mkdir -p /app/configs /app/data/clients \
    && chmod 755 /usr/local/bin/docker-entrypoint.sh \
    && chown -R app:app /app /opt/venv /usr/local/bin/docker-entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/health', timeout=3)" || exit 1

ENTRYPOINT ["docker-entrypoint.sh"]
