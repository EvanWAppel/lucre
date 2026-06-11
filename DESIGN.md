# Lucre — Design Decisions

Personal finance app ("like Rocket Money") for exactly one user: Evan.
Decisions below were resolved in a design interview on 2026-06-11 and supersede
the stack described in README.md.

## Scope

Four jobs, in scope for v1+:

1. **Balances & net worth** — all bank/card balances on one dashboard, net worth over time.
2. **Subscription detection** — find recurring charges, surface new ones, catch price increases.
3. **Spending by category** — track-only for v1: spend-per-category reporting, **no budget targets** yet.
4. **Bills & alerts** — bill calendar (derived from recurring detection + manual additions), email alerts.

Out of scope for v1: budget targets/envelopes, investments and loans via Plaid
(net worth can take manual balance entries later), multi-user, bill negotiation/cancellation.

## Architecture

- **One service**: Python FastAPI serving both API routes and server-rendered HTML
  (Jinja2 + HTMX). Installable as a PWA on the phone home screen. No Node/Next.js.
- **Database**: SQLite on a Railway persistent volume (SQLAlchemy models, as in `backend/`).
- **Hosting**: Railway, single service.
- **Backups**: Litestream running alongside the app, streaming the SQLite WAL to
  Cloudflare R2 (free tier). Restore = one litestream command.
- **Auth**: single hashed password from config + long-lived secure session cookie,
  rate-limited login route. (Single user; no accounts table.)
- **Email**: Resend (free tier) for the daily digest and urgent alerts.

## Data pipeline

- **Source**: Plaid **production** (pay-as-you-go). Products: Transactions (includes
  balances and `personal_finance_category`). No Investments/Liabilities/Recurring products.
- **Account types**: checking, savings, credit cards. Connected via Plaid Link;
  access tokens encrypted at rest (Fernet, as in `backend/crypto.py`).
- **Sync**: daily scheduled sync (in-process APScheduler or Railway cron) using
  `/transactions/sync` cursors. No webhooks.
- **Backfill**: 24 months of history on first connect (so annual subscriptions are
  detectable immediately).
- **Net worth history**: daily balance snapshot per account, written by the sync job.

## Features

- **Categorization**: Plaid's `personal_finance_category` as the default; manual
  recategorization in the UI; per-merchant override rules ("always Costco → Groceries")
  applied at sync time.
- **Recurring detection**: built in-house on raw transactions — same merchant +
  similar amount + regular interval (monthly and annual cadences). Powers the
  subscriptions list and seeds the bills calendar.
- **Bills**: detected recurring charges + manually added bills (rent, annual insurance),
  with editable predicted due dates.
- **Alerts** (computed during daily sync):
  - Urgent (immediate email): low balance below per-account threshold; single
    transaction above a configurable amount.
  - Digest (daily morning email): new recurring charge detected; price increase on a
    known recurring charge; upcoming bills.

## Milestones

1. **Balances dashboard** — Plaid Link connect flow, daily sync, password login,
   one screen with all balances + total. Proves the full pipeline
   (Plaid prod, Railway volume, Litestream, auth). ≈ the existing skeleton's scope.
2. Transactions list with categories + manual recategorization and merchant rules.
3. Recurring detection → subscriptions list; net worth history chart.
4. Bills calendar (derived + manual); email digest + urgent alerts.

## Engineering practice (from claude.md)

uv for all Python (`uv run`, `uv add`); TDD with pytest, fixtures in `conftest.py`;
ruff lint; ty typecheck; prek pre-commits; logging everywhere; never hide or wrap errors.

## Known issues to resolve when building

- `.env.example` sets `PLAID_ENV=development` — Plaid **retired the Development
  environment (June 2024)**. Use `sandbox` for tests and `production` (requires
  approval + billing setup on the Plaid dashboard) for real data.
- README.md still describes the old two-service Next.js + Postgres + Railway stack
  and needs rewriting to match this document.
- Git repo currently lives at `backend/.git`; with the single-service shape the repo
  root should move up to `lucre/`.
