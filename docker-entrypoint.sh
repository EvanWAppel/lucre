#!/usr/bin/env bash
# Note: intentionally no `set -e` — a litestream/R2 hiccup must never stop the app
# from booting. The database lives on the persistent /data volume; R2 is backup only.
set -uo pipefail

DB_PATH="${LUCRE_DB_PATH:-/data/lucre.db}"
mkdir -p "$(dirname "$DB_PATH")"

# Fresh volume? Pull the latest replica from R2 first. TIMEBOXED: `litestream
# restore` has no built-in timeout, so an unreachable/misconfigured R2 endpoint
# (e.g. the known Cloudflare per-account-endpoint TLS outage) would otherwise HANG
# here indefinitely and uvicorn would never start — the exact failure that broke
# the Railway healthcheck (see docs/lucre-railway-debug.md). `timeout` guarantees
# we fall through to the local DB instead of blocking boot.
timeout 30 litestream restore -if-db-not-exists -if-replica-exists "$DB_PATH" \
  || echo "litestream restore skipped/failed/timed out (R2 unreachable?); using local database"

# Replicate the DB to R2 continuously, in the BACKGROUND (reads /etc/litestream.yml).
# Running it detached — rather than `litestream replicate -exec uvicorn` — guarantees
# uvicorn starts even if litestream can't initialize (unreachable R2): replication is
# best-effort backup and must never gate availability. litestream retries R2 on its
# own while the app serves; it picks up /data/lucre.db once init_db() creates it.
litestream replicate &

# uvicorn is the primary (PID 1) process — it always starts, R2 up or down.
exec uv run --no-sync uvicorn main:app --host 0.0.0.0 --port "${PORT:-8000}"
