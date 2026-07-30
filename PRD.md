# Lucre — Product Requirements

Lucre is a single-user personal finance PWA (see [DESIGN.md](DESIGN.md) for the
core scope, architecture, and data pipeline). This document adds the
**dual-purpose** requirements resolved in a product interview on **2026-06-28**:
Lucre must work as **both**

1. a polished, public **portfolio piece** a recruiter can click through and judge,
   and
2. a private, real **finance tracker Evan uses daily on his phone**.

DESIGN.md remains the source of truth for the underlying app. Where this document
and DESIGN.md disagree, this document governs the recruiter/demo surfaces and
DESIGN.md governs the owner's real app.

## 1. The two audiences

| | **Recruiter / visitor** | **Owner (Evan)** |
|---|---|---|
| Goal | Judge engineering + product skill in <5 min | Track real finances |
| Sees | Intro screen → demo app (fake data) → About page; repo as deepest layer | Real balances, net worth, subscriptions, bills, alerts |
| Auth | None (anonymous demo session) | Password login → long-lived session |
| Data | Ephemeral, per-visitor, fake | Real, persistent (existing SQLite DB) |
| Device | Mostly desktop, must also work on mobile | Phone PWA (home-screen icon → authenticated real dashboard) |
| Primary recruiter framing | **Eng leadership / generalist** — product thinking, decisions, tradeoffs, "a real thing I use" | — |

The single hardest constraint: **a visitor must never see, reach, or mutate
Evan's real financial data**, while still experiencing the full working app.

## 2. Surfaces & entry flow

One deployment, one codebase. Three recruiter-facing surfaces plus the real app.

1. **Intro / launch screen** (`/`, anonymous) — a one-screen framing: 3–4 sentence
   description of what Lucre is and why it was built, a compact stack summary
   (badges), and a prominent **"Launch demo"** button. Also links to GitHub and
   the About page. This is the first impression; it is held to the high polish bar
   (§7).
2. **Demo app** — the full Lucre UI running on **ephemeral, per-visitor, fake
   data** (§4). Every screen works. A slim persistent banner reads **"Demo — this
   is fake data"** with a link back to the intro/About and to GitHub.
3. **About / Architecture page** (`/about`, public) — the fuller engineering
   story: architecture diagram, key decisions and tradeoffs (distilled from
   DESIGN.md), and Evan's identity/links (§6). Self-contained so a recruiter never
   *has* to leave the site, with the repo as the deepest optional layer.
4. **Real app** (owner-only) — the existing authenticated Lucre. Reached via a
   **discreet "Sign in" link** and `/login`. Evan's phone PWA opens straight to the
   authenticated real dashboard.

### Entry flow

- Anonymous visitor hits `/` → intro screen → "Launch demo" → demo app.
- Recruiter can jump to `/about` or GitHub at any time from the banner/intro.
- Evan taps his phone home-screen icon → already-authenticated real dashboard
  (session lasts ~1 year, as today). If logged out, the discreet "Sign in" link →
  `/login` → real app.

## 3. Session model & roles

The app today is genuinely single-user (one SQLite DB, one hashed password, no
accounts table). Demo mode introduces a **session role** without introducing user
accounts:

- **`anonymous` / `demo`** — no login. On first request (or on "Launch demo") the
  server provisions an ephemeral demo session (§4). All reads/writes for this
  session are routed to that session's throwable store. This role can **never**
  read or write the real tables.
- **`owner`** — authenticated via the existing password + session cookie. Reads
  and writes the real SQLite DB exactly as today.

Routing rule (must be enforced centrally, not per-handler): the data-access layer
selects the backing store from the session role. There is no code path where a
demo session can resolve to the real database.

## 4. Demo data: ephemeral, per-visitor, isolated

**Behavior:** each visitor gets their **own fresh copy** of a seed dataset, can
edit it freely (recategorize, add bills, change thresholds, etc.), and it
**auto-resets** when their session expires or goes idle. Two visitors never see
each other's changes.

**Storage (recommended):** copy the seed fixture into a **per-session in-memory /
temp SQLite** keyed by the demo session id; discard on idle/expiry. The real DB
file is never opened for writes by a demo session.

- Reconciliation note: the "same DB, role flag" decision applies to the **owner's
  real data** (it stays in the existing SQLite DB, reached by flipping to owner
  mode via login). The **demo** data lives *outside* the real tables, per the
  isolation rule above. These two decisions are complementary, not in conflict.
- The namespaced-rows alternative (demo rows tagged with `demo_session_id` in the
  same file + a purge job) was considered and **rejected** for v1: it mixes fake
  rows into the real DB and risks leakage. Revisit only if per-session SQLite
  proves operationally heavy.

**Lifecycle / limits:**

- Idle TTL for a demo session (e.g. ~30 min) after which its store is reset/freed.
- Per-session resource caps and a global cap on concurrent demo sessions so
  anonymous traffic cannot exhaust the host.
- Demo sessions **never** call Plaid (sandbox or prod) and **never** send email.
  Any action that would (e.g. "connect a bank", "send digest") is simulated
  in-app (§5, §4 seed).

### Seed dataset narrative

The fake data is what recruiters actually see working, so it is specified, not
incidental. The seed must simultaneously read as a real person's finances **and**
deliberately trigger every "smart" feature:

- **Healthy, realistic finances** — plausible salary, checking + savings + ~2
  credit cards, ~6 months of history, steady net-worth growth.
- **Triggers the smart features** — the data deliberately contains:
  - a **newly appeared** recurring subscription (fires "new subscription"
    detection/alert),
  - a **price increase** on an existing recurring charge (fires "price increase"
    alert),
  - a **low-balance** moment on an account (fires the low-balance urgent alert),
  - a **large single transaction** (fires the large-transaction urgent alert).
- **Variety of spend categories** — groceries, dining, travel, utilities, etc., so
  the spending-by-category screen looks substantive.
- **Mixed cadences** — both **monthly and annual** subscriptions, so the
  recurring-detection cadence logic is visibly exercised.

The seed should be generated deterministically (same story every time) but
relative to "now" so history/dates always look current.

## 5. Demo depth & feature showcase

- **Full UI on fake data.** Every screen is reachable and interactive in demo:
  dashboard/balances, net-worth chart, transactions + manual recategorization +
  merchant rules, subscriptions list, bills calendar, alerts.
- **Simulated bank connect in demo.** The demo *makes it look like* a visitor can
  connect a bank: a "Connect a bank" button opens a convincing mock of the
  institution-picker / Link experience, and on "completion" new accounts +
  transactions appear in their sandbox as if a sync just ran. **No real Plaid call
  is ever made** (no flakiness, no abuse surface, no credentials). The real Plaid
  Link sandbox/prod flow is owner-only; the genuine integration is described on the
  About page and lives in the code.
- **Email/alerts shown as in-app preview.** Because the daily digest + urgent
  alerts are a real, differentiating feature, the demo renders an **in-app preview
  of exactly what those emails look like**, populated from the seed data. It never
  sends. This is a primary showcase screen.

## 6. About page & identity

The About page tells the engineering story and lets a recruiter act on it:

- Architecture diagram + the key decisions/tradeoffs (single FastAPI service,
  HTMX/PWA, SQLite + Litestream → R2, in-house recurring detection, Plaid prod
  pipeline, the demo-isolation design itself — which is itself a nice systems-design
  talking point).
- A short teaser of this story also appears on the intro screen ("both" placement).
- **Identity block:** "Built by **Evan Appel**" + a short role tagline; links to
  **GitHub** (repo/profile), **LinkedIn**, and **resume (PDF) / contact email**.

## 7. Visual polish — graded requirement

Visual quality is a **first-class requirement** with acceptance criteria, not a
nice-to-have, because recruiters judge on sight. Applies to all surfaces (intro,
demo app, About, and — since it's the same UI — the real app benefits too).

Acceptance criteria:

- Consistent type scale, spacing, and color system; the **Lucre logo**
  ([Lucre.svg](Lucre.svg)) used in the header/intro.
- **Fully responsive**: looks right on a phone (Evan's daily use) and on a
  recruiter's desktop. No horizontal scroll, tap targets sized for mobile.
- **Dark mode** supported (respect system preference).
- Charts (net worth, spending) are legible and styled, not default/raw.
- PWA: installable, themed splash/icon, offline-tolerant shell where reasonable.
- No visible debug output, broken layouts, or placeholder lorem in any
  recruiter-reachable surface.

## 8. Public exposure & security posture

- The deployed URL is meant to be **put on Evan's resume/LinkedIn** and is
  **search-indexable**.
- **Rate limiting** on demo-session creation and on write actions; per-session and
  global concurrency caps (§4).
- The existing **login route stays rate-limited** (as in DESIGN.md).
- Demo sessions are sandboxed from real data, Plaid, and email (§3–§5).
- `/login` and the real app are not prominently advertised but are not secret; the
  discreet "Sign in" link is acceptable.
- Nothing about the owner's real data, balances, or Plaid tokens is ever exposed to
  an anonymous session, in markup, APIs, or error messages.

## 9. Non-goals (for this dual-purpose layer)

- No multi-user accounts. Roles are `anonymous/demo` and `owner` only.
- No *real* Plaid connect for anonymous visitors — the demo connect flow is a
  simulation only (no Plaid call).
- No real email sent from demo.
- No persistence of demo edits across sessions.
- Core finance scope and out-of-scope items remain as defined in DESIGN.md
  (no budget targets, no investments/loans via Plaid, etc.).

## 10. Open questions / decide-at-build-time

- Exact demo-session idle TTL and global concurrency cap (tune against host
  resources).
- Whether the per-session store is SQLite `:memory:`, a temp file copied from a
  template, or an equivalent — pick during implementation; isolation guarantee is
  the requirement, the mechanism is not.
- Resume PDF hosting (in-repo asset vs external link).
