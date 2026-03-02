#!/bin/sh
set -eu

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
UVICORN_WORKERS="${UVICORN_WORKERS:-1}"

exec python -m uvicorn backend.app:app \
  --host "${HOST}" \
  --port "${PORT}" \
  --workers "${UVICORN_WORKERS}"
