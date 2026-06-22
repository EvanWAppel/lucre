#!/usr/bin/env bash
# Note: intentionally no `set -e` — a litestream/R2 hiccup must never stop the app
# from booting. The database lives on the persistent /data volume; R2 is backup only.
set -uo pipefail

DB_PATH="${LUCRE_DB_PATH:-/data/lucre.db}"
mkdir -p "$(dirname "$DB_PATH")"

# Fresh volume? Pull the latest replica from R2 first. Non-fatal: if R2 is unreachable
# (e.g. the known Cloudflare per-account-endpoint TLS outage) we serve the local DB.
litestream restore -if-db-not-exists -if-replica-exists "$DB_PATH" \
  || echo "litestream restore skipped/failed (R2 unreachable?); using local database"

# Run uvicorn under litestream so the DB is continuously replicated to R2. If litestream
# can't run (R2 down), fall through to plain uvicorn so the app stays up; replication
# resumes on the next deploy once R2 recovers.
litestream replicate -exec \
  "uv run --no-sync uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"

echo "litestream replicate exited; starting uvicorn without replication"
exec uv run --no-sync uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
