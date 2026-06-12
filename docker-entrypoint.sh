#!/usr/bin/env bash
set -euo pipefail

DB_PATH="${LUCRE_DB_PATH:-/data/lucre.db}"
mkdir -p "$(dirname "$DB_PATH")"

# Fresh volume? Pull the latest replica from R2 before serving anything.
litestream restore -if-db-not-exists -if-replica-exists "$DB_PATH"

exec litestream replicate -exec \
  "uv run --no-sync uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"
