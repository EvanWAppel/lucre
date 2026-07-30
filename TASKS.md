# Lucre — Task Board

Implements [DESIGN.md](DESIGN.md) (core app) and [PRD.md](PRD.md) (demo mode /
recruiter showcase — **Group H**). Check off tasks as they complete.

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
                                                       │
   (C·D·E·F·G all shipped) ───────────────────────────┴──► H (demo & showcase)

   H1 (role) ─► H2 (per-session store) ─► H4 (routing guard) ──┐   ◄─ H3 (seed) feeds H2/H8/H9
                                                               ├─► H6  intro/launch
                                                               ├─► H7  demo banner
                                                               ├─► H8  simulated connect  (needs C/E data)
                                                               ├─► H9  email preview       (needs G)
                                                               ├─► H10 About + identity
                                                               └─► H11 owner sign-in
                          H5 (lifecycle/limits) ┘
   (surfaces done) ──► H12 safety sweep ─► H13 polish ─► H14 isolation test ─► H15 exposure
```

Parallelization: **A** first (quick, mostly sequential). **B** is the critical path — one
agent drives it end-to-end. Once B6 lands, **C**, **E**, and **G** lanes can each be taken
by a separate agent. **D2–D4** are pure functions with no model dependencies and can be
built by another agent *anytime after A4*. **F** needs D's models. **H** comes last: it
showcases features that must already work. Within H, the isolation core is sequential
(**H1 → H2 → H4**, with **H3** seed and **H5** limits buildable in parallel); once the guard
lands, the surface tasks **H6–H11** can be split across agents, then **H12–H15** close out
safety, polish, and exposure. **H4 and H14 are security-critical** — no demo session may ever
reach the real DB, Plaid, or email.

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
- [x] **B15** OAuth institution support (needed for Chase and most major banks): register the
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
- [x] **D4** Persistence: `RecurringSeries` model (merchant_key, cadence, median_amount,
      last_seen, next_expected, active, dismissed). Diff-and-upsert from detector output;
      newly seen series and price increases are recorded as rows in `AlertEvent` (see G1 —
      coordinate or stub). Tests: new series detected once, not re-flagged next sync.
- [x] **D5** Wire into daily sync after transactions ingest (needs C2). Integration test:
      sync of fixture history yields expected series.
- [x] **D6** Subscriptions page `GET /subscriptions`: active series with amount, cadence,
      next expected date, annualized cost total; "not a subscription" dismiss button
      (sets `dismissed`, excluded thereafter). Tests.

## Group E — Net worth (after B6; small lane, pairs well with C agent)

- [x] **E1** `BalanceSnapshot` model (account FK, date, balance; unique account+date).
      Daily sync writes one per account, idempotent on re-run. Tests.
- [x] **E2** Net-worth series service: per-day total (cash − credit), carrying forward the
      latest snapshot for accounts missing that day. Pure + tested.
- [x] **E3** Dashboard chart: net-worth sparkline (30/90/365 toggles) — server-computed
      points, lightweight rendering (inline SVG fine). Test: correct points in response.

## Group F — Bills (after D4)

- [x] **F1** `Bill` model: either derived (FK → RecurringSeries) or manual (name, amount,
      cadence, next_due), with `due_day_override` and autopay flag. Tests.
- [x] **F2** Seed/refresh derived bills from active recurring series during sync; series
      dismissal hides its bill. Tests.
- [x] **F3** Manual bill CRUD: add/edit/delete pages for bills detection can't see (rent,
      annual insurance). Tests.
- [x] **F4** Upcoming-bills view `GET /bills`: next-30-days list (date, name, expected amount,
      source badge), monthly total. Due-date prediction honors overrides. Tests including
      month-boundary cases (due on the 31st, February).

## Group G — Alerts & email (G1/G2/G5 can start after B6, parallel lane)

- [x] **G1** `AlertEvent` model: type, dedupe_key, payload JSON, created_at, emailed_at,
      urgency. Dedupe: same key never recorded twice. Tests.
- [x] **G2** `AlertSettings` (singleton row: per-account low-balance thresholds, large-txn
      amount) + `GET /settings` page to edit them, plus password-change later. Tests.
- [x] **G3** Post-sync rules: low balance (urgent) and large transaction (urgent) emit
      AlertEvents per G2 settings. Tests: fires once, respects thresholds, no repeat while
      balance stays low (dedupe by day).
- [x] **G4** Digest sources: new-subscription + price-increase events (from D4) and
      bills due within 3 days (from F4) marked as digest urgency. Tests.
- [x] **G5** Email sender `backend/services/email.py`: Resend API wrapper (httpx), `send(subject,
      html)`; fake in tests; urgent events email immediately at creation. Failure logged
      loudly, never swallowed. Tests.
- [x] **G6** Daily digest: 07:30 scheduler job renders a Jinja email (yesterday's spend, new
      subscriptions, price increases, upcoming bills, current balances) from un-emailed
      digest events, marks them `emailed_at`. Tests: renders, marks, skips when empty.
- [ ] **G7 [HUMAN]** Verify real digest + an urgent alert arrive in Gmail and look right on
      the phone.

## Group H — Demo mode & recruiter showcase (after the app works end-to-end)

Implements [PRD.md](PRD.md): one deployment that is both a public, recruiter-facing
showcase (sandboxed demo, fake data, no login) and Evan's private finance tracker.
Most of H depends on the relevant feature existing first (a screen must work before
it can be demoed/polished); the session/store/isolation core (H1–H4) comes first
within the group. **The load-bearing requirement is isolation: a demo session must
never read or write the real tables, call Plaid, or send email — H4 + H14 prove it.**

- [x] **H1** Session role: extend the auth/session layer so every request resolves a
      role — `owner` (authenticated, as today) or `anonymous`/`demo` (no login). Helpers
      `is_demo()` / `is_owner()` available to handlers and templates. Tests: anonymous
      request is `demo`, authenticated is `owner`.
- [x] **H2** Per-session demo store: provision an ephemeral, per-demo-session SQLite
      (`:memory:` or temp file copied from a seed template), keyed by the demo session id,
      torn down on idle/expiry. Tests: two demo sessions get independent data; expiry frees
      the store.
- [x] **H3** Seed generator `backend/services/demo_seed.py`: deterministic-but-current fake
      dataset per the PRD narrative — plausible salary + checking/savings/2 cards, ~6 months
      history, steady net-worth growth, varied spend categories, monthly **and** annual
      subscriptions, and deliberate triggers (a new subscription, a price increase, a
      low-balance moment, a large transaction). Pure builder over the existing models. Tests:
      detection + alert rules fire on the seed (new sub, price increase, low balance, large
      txn all present).
- [x] **H4** Data-layer routing + guard (**security-critical**): the DB dependency selects the
      backing store from the session role; there is no code path where a demo session resolves
      to the real DB. Tests: a demo session's reads/writes hit only its store; assert the real
      DB file is never opened for write under a demo session.
- [x] **H5** Demo lifecycle & limits: idle TTL for demo sessions, a global cap on concurrent
      demo stores, and rate limiting on demo-session creation + demo write actions. Tests:
      session resets after TTL; creation past the cap is refused gracefully.
- [x] **H6** Intro / launch screen `GET /` (anonymous): one-screen framing (what Lucre is +
      why), compact stack summary, **"Launch demo"** button, links to GitHub and `/about`. Held
      to the H13 polish bar. Test: renders with the demo CTA for anonymous, skipped for owner
      (owner lands on the real dashboard).
- [x] **H7** Demo context banner: slim persistent "Demo — this is fake data" bar shown only in
      demo sessions, linking to intro/About and GitHub. Test: present for demo, absent for owner.
- [x] **H8** Simulated bank-connect flow: a "Connect a bank" action in demo opens a convincing
      mock institution-picker / Link experience and, on "completion", makes new accounts +
      transactions appear in the visitor's sandbox as if a sync ran. **No Plaid call.** Tests:
      the demo connect path never touches `plaid_client`; new seeded accounts appear afterward.
- [x] **H9** In-app email/alert preview `GET /alerts/preview`: renders exactly what the daily
      digest + urgent-alert emails look like, populated from the (seed) data, never sending.
      Reachable in demo as a showcase screen. Test: preview renders digest + urgent layouts.
- [x] **H10** About / Architecture page `GET /about` (public): architecture diagram, key
      decisions/tradeoffs distilled from DESIGN.md + the demo-isolation design, and an identity
      block — "Built by Evan Appel" + tagline, GitHub, LinkedIn, resume/contact. Test: page
      renders with the identity links.
- [x] **H11** Discreet owner access: a small "Sign in" link → `/login`; owner's phone PWA opens
      straight to the authenticated real dashboard. Test: link present, `/login` reachable,
      authenticated root shows the real app not the intro.
- [x] **H12** Demo safety sweep: ensure demo sessions cannot send email (H9 preview only) or
      call Plaid (real Link/sync are owner-gated). Tests: email sender and `plaid_client` are
      never invoked under a demo session across the demo-reachable routes.
- [x] **H13** Visual-polish pass (graded — see PRD §7): consistent type/spacing/color system,
      Lucre logo in header/intro, full mobile↔desktop responsiveness, dark mode (system pref),
      styled legible charts, themed PWA install. Acceptance: no horizontal scroll on mobile,
      mobile-sized tap targets, no debug/placeholder content on any recruiter-reachable surface.
- [x] **H14** Isolation integration test (**security-critical**): drive the full demo flow via
      TestClient (launch → edit → simulated connect → preview) and assert the real DB is
      untouched and no real rows are ever served to a demo session.
- [x] **H15** Public exposure: make the demo indexable (sitemap/robots allow), add `noindex` on
      `/login` and owner-only views, confirm rate limits from H5 are live. Put the deployed URL
      on resume/LinkedIn. **[HUMAN]** for the resume/LinkedIn edits.
- [x] **H16 [HUMAN]** Host the resume PDF (in-repo asset vs external link — PRD §10) and wire it
      into the About page identity block.
