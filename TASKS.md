# Lucre — Task Board

Implements [DESIGN.md](DESIGN.md). Check off tasks as they complete.

## Conventions (apply to every task)

- **TDD**: write the failing test first (`backend/tests/`), make it pass, refactor.
  Shared fixtures live in `backend/tests/conftest.py`.
- Run before checking off: `uv run pytest && uv run ruff check . && uv run ty check`
- All Python through `uv run`; add deps with `uv add LIB` / `uv add --dev LIB`. Never edit
  `pyproject.toml` dependencies by hand.
- Use `logging`; never hide or wrap errors.
- Tasks marked **[HUMAN]** need Evan (dashboards, billing, phone) — agents should skip them
  and flag when they become blockers.

## Dependency graph

```
A (foundation) ──► B (vertical slice) ──┬─► C (transactions) ──► D (recurring) ──► F (bills)
                                        ├─► E (net worth)                          │
                                        └─► G1/G2/G5 (alert core) ◄── D5, F4 ──────┘
```

Parallelization: **A** first (quick, mostly sequential). **B** is the critical path — one
agent drives it end-to-end. Once B6 lands, **C**, **E**, and **G** lanes can each be taken
by a separate agent. **D2–D4** are pure functions with no model dependencies and can be
built by another agent *anytime after A4*. **F** needs D's models.

---

## Group A — Foundation (do first)

- [x] **A1** Move the git root: repo currently lives at `backend/.git`; re-init (or `git mv`
      history-preserving) so the repo root is `lucre/`, with a root `.gitignore` covering
      `.venv`, `*.db`, `.env`.
- [x] **A2** Fix `backend/config.py`: default `plaid_env="sandbox"`, validate it is
      `sandbox|production` (test: invalid value raises). Add settings: `app_password_hash`,
      `session_secret`, `resend_api_key`, `alert_from_email`, `alert_to_email`.
- [x] **A3** Update `.env.example` to match A2 (drop `development`, `DATABASE_URL` becomes a
      SQLite path like `sqlite:///data/lucre.db`).
- [x] **A4** SQLite-ify `backend/database.py`: `connect_args={"check_same_thread": False}`,
      enable WAL + foreign-keys pragmas on connect, drop Postgres pool args. Remove
      `psycopg2-binary` (`uv remove psycopg2-binary`). Test: `init_db()` creates tables in a
      tmp-path SQLite file.
- [x] **A5** Create `backend/tests/conftest.py` fixtures: in-memory SQLite engine + session
      (function-scoped, fresh schema), `TestClient` with `get_db` override, settings override
      fixture, and a `FakePlaidClient` stub (canned link-token / exchange / accounts /
      transactions-sync responses, used everywhere Plaid is mocked).
- [x] **A6** Tooling: `uv add --dev ty prek`; add `prek` config running ruff (lint+format) and
      ty; install the git hook. Verify `uv run prek run --all-files` passes.
- [x] **A7** Logging setup: `logging.basicConfig` (level from env, default INFO) wired into app
      startup; uvicorn access logs on.
- [ ] **A8 [HUMAN]** Apply for Plaid **production** access in the dashboard (approval takes
      days — start now; everything until B12 runs on sandbox).
- [ ] **A9 [HUMAN]** Create Cloudflare R2 bucket + access keys for Litestream; create Resend
      account + API key; have Railway account ready.

## Group B — Vertical slice (critical path; one agent, in order)

Goal: a deployed, password-protected page on your phone showing real (sandbox) balances,
synced daily. Smallest end-to-end proof of the whole pipeline.

- [x] **B1** `backend/main.py`: FastAPI app factory, `init_db()` on startup, `GET /health` →
      `{"status": "ok"}`. Test via TestClient.
- [x] **B2** Server-rendered shell: `uv add jinja2`; `templates/base.html` (HTMX from CDN,
      viewport meta), `static/` mount, PWA `manifest.json` + minimal service worker + icon.
      Test: `GET /` returns HTML containing the app shell.
- [x] **B3** Auth: `uv add argon2-cffi itsdangerous`; password check against
      `app_password_hash`, signed session cookie (1-year expiry, `HttpOnly`, `Secure`,
      `SameSite=Lax`), login page, logout, dependency that redirects anonymous requests to
      `/login`. In-memory rate limit: 5 failed attempts → 15-min lockout. Tests: wrong/right
      password, redirect, lockout. Plus a `scripts/hash_password.py` helper.
- [x] **B4** Plaid client module `backend/plaid_client.py`: thin wrapper exposing
      `create_link_token()`, `exchange_public_token(token)`, `get_accounts(access_token)`.
      Real Plaid SDK behind an interface the `FakePlaidClient` fixture implements. Tests use
      the fake only.
- [x] **B5** Link flow: `GET /link` page embedding Plaid Link JS; `POST /api/plaid/exchange`
      exchanges the public token, stores `Item` (Fernet-encrypted access token via
      `crypto.py`) + its `Account` rows. Test: posting a fake public token persists item +
      accounts; duplicate `plaid_item_id` rejected cleanly.
- [x] **B6** Balance sync service `backend/services/sync.py`: for each Item, fetch accounts,
      upsert `Account` rows, `touch()` balances. Idempotent. Tests: new account appears,
      existing balance updates, one failing item doesn't abort the others (error logged,
      not swallowed).
- [x] **B7** Dashboard `GET /`: accounts grouped by type (cash / credit), per-account balance,
      headline total (cash − credit), `last_refreshed_at`. Test: seeded accounts render with
      correct total.
- [x] **B8** "Sync now" button: HTMX `POST /api/sync` runs B6 and re-renders the dashboard
      fragment. Test: balance change visible in response.
- [x] **B9** Scheduler: `uv add apscheduler`; daily sync job (07:00 America/New_York) started
      with the app, guarded so TestClient never starts it. Test: job is registered with
      correct trigger.
- [ ] **B10** Deploy: Dockerfile (uv-based, runs litestream as supervisor →
      `litestream replicate -exec "uvicorn main:app ..."`), `litestream.yml` (R2 replica,
      restore-if-missing on boot), Railway service + volume mounted at `/data`, env vars set.
      Sandbox creds. **[HUMAN]** assists with Railway dashboard bits.
- [ ] **B11** Backup restore drill: delete the local copy, restore from R2 with
      `litestream restore`, confirm data intact. Document the command in README.
- [ ] **B12 [HUMAN]** Plaid production approved → flip `PLAID_ENV=production`, connect real
      checking/savings/credit accounts via `/link`.
- [ ] **B13 [HUMAN]** Add PWA to phone home screen; confirm login survives a week.
- [ ] **B15** OAuth institution support (needed for Chase and most major banks): register the
      deployed `https://<app>/link` URL as an allowed redirect URI in the Plaid dashboard
      **[HUMAN]**, pass `redirect_uri` in `create_link_token()`, and re-initialize Link with
      `received_redirect_uri` when the user lands back on `/link?oauth_state_id=...`.
      Test: link token request includes the redirect URI.
- [x] **B14** Rewrite `README.md` to match DESIGN.md (single service, SQLite, Railway volume,
      Litestream, run/deploy/restore instructions).

## Group C — Transactions & categories (after B6; one agent)

- [x] **C1** Models: `Transaction` (plaid_transaction_id unique, account FK, date, name,
      merchant_name, amount, plaid_category, user_category, pending) and `Item.sync_cursor`.
      Tests: round-trip, uniqueness.
- [x] **C2** Cursor sync: extend `plaid_client` + sync service with `/transactions/sync` —
      apply `added`/`modified`/`removed`, paginate `has_more`, persist cursor per item.
      Tests with multi-page fake responses, including a removed-transaction case.
- [x] **C3** First-sync backfill pulls full available history (24 months) by paging from a
      null cursor. Test: large fake history fully ingested, cursor saved.
- [x] **C4** Effective-category logic: `user_category` overrides `plaid_category`; expose
      `Transaction.effective_category`. Pure + tested.
- [x] **C5** Transactions page `GET /transactions`: month + account + category filters, HTMX
      pagination (50/page), pending styled distinctly. Tests for filters.
- [x] **C6** Recategorize: inline select posts `PATCH /api/transactions/{id}/category`. Test:
      override persists, effective category changes.
- [x] **C7** Merchant rules: `MerchantRule` model (merchant_key → category); "always apply to
      this merchant" option when recategorizing, applied to incoming transactions at sync
      and (optionally) retroactively. Tests: future txn auto-categorized; retro apply.
- [x] **C8** Spending view `GET /spending`: month picker, total + per-category sums (effective
      category) with simple CSS bar chart. Test: sums correct, refunds/credits handled.

## Group D — Recurring detection (pure logic; can start after A5, parallel with B/C)

- [x] **D1** Merchant normalization `backend/services/merchants.py`: collapse case, strip
      store numbers / city suffixes / trailing IDs ("NETFLIX.COM 866-...", "STARBUCKS #1234")
      into a stable `merchant_key`. Pure function, table-driven tests with ugly real-world
      strings.
- [x] **D2** Detector core `backend/services/recurring.py`: given a list of (merchant_key,
      date, amount) tuples, return series with cadence (weekly/monthly/annual), median
      amount, last_seen, predicted next date. Tolerances: ±3 days monthly, ±10 days annual,
      amount within 15%. Pure function. Golden tests: Netflix monthly, annual Prime, variable
      utility bill, gas-station noise that must NOT match.
- [x] **D3** Price-increase rule: series' newest amount > 5% above its trailing median →
      flagged with old/new amounts. Pure + tested.
- [ ] **D4** Persistence: `RecurringSeries` model (merchant_key, cadence, median_amount,
      last_seen, next_expected, active, dismissed). Diff-and-upsert from detector output;
      newly seen series and price increases are recorded as rows in `AlertEvent` (see G1 —
      coordinate or stub). Tests: new series detected once, not re-flagged next sync.
- [ ] **D5** Wire into daily sync after transactions ingest (needs C2). Integration test:
      sync of fixture history yields expected series.
- [ ] **D6** Subscriptions page `GET /subscriptions`: active series with amount, cadence,
      next expected date, annualized cost total; "not a subscription" dismiss button
      (sets `dismissed`, excluded thereafter). Tests.

## Group E — Net worth (after B6; small lane, pairs well with C agent)

- [ ] **E1** `BalanceSnapshot` model (account FK, date, balance; unique account+date).
      Daily sync writes one per account, idempotent on re-run. Tests.
- [ ] **E2** Net-worth series service: per-day total (cash − credit), carrying forward the
      latest snapshot for accounts missing that day. Pure + tested.
- [ ] **E3** Dashboard chart: net-worth sparkline (30/90/365 toggles) — server-computed
      points, lightweight rendering (inline SVG fine). Test: correct points in response.

## Group F — Bills (after D4)

- [ ] **F1** `Bill` model: either derived (FK → RecurringSeries) or manual (name, amount,
      cadence, next_due), with `due_day_override` and autopay flag. Tests.
- [ ] **F2** Seed/refresh derived bills from active recurring series during sync; series
      dismissal hides its bill. Tests.
- [ ] **F3** Manual bill CRUD: add/edit/delete pages for bills detection can't see (rent,
      annual insurance). Tests.
- [ ] **F4** Upcoming-bills view `GET /bills`: next-30-days list (date, name, expected amount,
      source badge), monthly total. Due-date prediction honors overrides. Tests including
      month-boundary cases (due on the 31st, February).

## Group G — Alerts & email (G1/G2/G5 can start after B6, parallel lane)

- [ ] **G1** `AlertEvent` model: type, dedupe_key, payload JSON, created_at, emailed_at,
      urgency. Dedupe: same key never recorded twice. Tests.
- [ ] **G2** `AlertSettings` (singleton row: per-account low-balance thresholds, large-txn
      amount) + `GET /settings` page to edit them, plus password-change later. Tests.
- [ ] **G3** Post-sync rules: low balance (urgent) and large transaction (urgent) emit
      AlertEvents per G2 settings. Tests: fires once, respects thresholds, no repeat while
      balance stays low (dedupe by day).
- [ ] **G4** Digest sources: new-subscription + price-increase events (from D4) and
      bills due within 3 days (from F4) marked as digest urgency. Tests.
- [ ] **G5** Email sender `backend/services/email.py`: Resend API wrapper (httpx), `send(subject,
      html)`; fake in tests; urgent events email immediately at creation. Failure logged
      loudly, never swallowed. Tests.
- [ ] **G6** Daily digest: 07:30 scheduler job renders a Jinja email (yesterday's spend, new
      subscriptions, price increases, upcoming bills, current balances) from un-emailed
      digest events, marks them `emailed_at`. Tests: renders, marks, skips when empty.
- [ ] **G7 [HUMAN]** Verify real digest + an urgent alert arrive in Gmail and look right on
      the phone.
