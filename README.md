# Lucre

Single-user personal finance PWA — balances, net worth, subscriptions, spending,
and bill alerts. Design decisions live in [DESIGN.md](DESIGN.md); the task board
is [TASKS.md](TASKS.md).

## Stack

- **App**: one Python FastAPI service serving server-rendered HTML (Jinja2 + HTMX),
  installable as a PWA
- **Database**: SQLite on a Railway volume, continuously replicated to Cloudflare R2
  with [Litestream](https://litestream.io)
- **Bank data**: [Plaid](https://plaid.com) (sandbox for development, production for real data)
- **Email**: [Resend](https://resend.com) for the daily digest and urgent alerts
- **Hosting**: [Railway](https://railway.app), single service

## Development

Prerequisites: [uv](https://docs.astral.sh/uv/), a Plaid account (sandbox keys are free).

```bash
cp .env.example .env   # fill in values; see comments in the file
cd backend
uv sync
uv run pytest                                  # tests
uv run uvicorn main:app --reload --port 8000   # run the app
```

Lint/typecheck/pre-commit:

```bash
uv run ruff check . && uv run ty check
uv run prek install   # one-time: installs the git hook
```

Generate secrets for `.env`:

```bash
uv run python scripts/hash_password.py   # APP_PASSWORD_HASH
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # ENCRYPTION_KEY
uv run python -c "import secrets; print(secrets.token_urlsafe(32))"  # SESSION_SECRET
```

## Deployment (Railway)

The root `Dockerfile` runs the app under Litestream
(`litestream replicate -exec uvicorn ...`), restoring the database from R2 on a
fresh volume.

1. Create a Railway service from this repo; attach a volume mounted at `/data`.
2. Set env vars: everything in `.env.example` (with
   `DATABASE_URL=sqlite:////data/lucre.db`) plus `LITESTREAM_ENDPOINT`,
   `LITESTREAM_BUCKET`, `LITESTREAM_ACCESS_KEY_ID`, `LITESTREAM_SECRET_ACCESS_KEY`
   for the R2 bucket.
3. The daily balance sync runs in-process at 07:00 America/New_York
   (`LUCRE_ENABLE_SCHEDULER=1`, set in the Dockerfile).

### Restore from backup

```bash
litestream restore -config litestream.yml /data/lucre.db
```

## Phone

Open the deployed URL in Safari → Share → Add to Home Screen. Log in once; the
session lasts a year.
