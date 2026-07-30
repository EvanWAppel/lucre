# Lucre — Production Checklist

Everything the code can't do for you. Work top to bottom: the accounts come
first, then secrets, then deploy, then flip to real bank data, then verify.

Task IDs in brackets map to `TASKS.md`.

---

## 1. Accounts & external services  `[A9]`

- [ ] **Railway** — create account + a new project. You'll add one service (this repo) and one persistent volume mounted at `/data`.
- [ ] **Cloudflare R2** — create a bucket for Litestream backups (e.g. `lucre-backups`). Create an R2 **API token** (Access Key ID + Secret). Note your account-scoped S3 endpoint: `https://<account-id>.r2.cloudflarestorage.com`.
  - ⚠️ Known gotcha (already handled in `docker-entrypoint.sh`): Cloudflare's per-account endpoint has had TLS outages. Boot is timeboxed so an unreachable R2 won't block the app — but double-check the endpoint value.
- [ ] **Resend** — create account, verify a sending domain (or use their onboarding sender), generate an API key. Needed for alert/digest email.
- [ ] **Plaid** — you already have sandbox creds. Start the **production access** application now — approval takes days. `[A8]`

---

## 2. Generate secrets

Run these locally and stash the output somewhere safe (password manager):

- [ ] **Fernet encryption key** (encrypts Plaid access tokens at rest):
  ```
  uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- [ ] **Session signing secret**:
  ```
  uv run python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```
- [ ] **App password hash** (your login password):
  ```
  uv run python scripts/hash_password.py
  ```

---

## 3. Railway environment variables

Set these on the Railway service (from `.env.example` + `litestream.yml`). **Do not** commit real values — `.env` is gitignored.

**App**
- [ ] `DATABASE_URL=sqlite:////data/lucre.db`  ← note the 4 slashes (absolute path into the mounted volume)
- [ ] `ENCRYPTION_KEY=` (from step 2)
- [ ] `SESSION_SECRET=` (from step 2)
- [ ] `APP_PASSWORD_HASH=` (from step 2)
- [ ] `COOKIE_SECURE=true`  (or leave unset — defaults true; must be true over HTTPS)

**Plaid** (sandbox first)
- [ ] `PLAID_CLIENT_ID=`
- [ ] `PLAID_SECRET=`
- [ ] `PLAID_ENV=sandbox`  (flip to `production` at step 6)
- [ ] `PLAID_REDIRECT_URI=`  (set at step 5 once you know the deployed URL)

**Email (Resend)**
- [ ] `RESEND_API_KEY=`
- [ ] `ALERT_FROM_EMAIL=`  (on your verified domain)
- [ ] `ALERT_TO_EMAIL=`  (where you want alerts — likely appelew@gmail.com)

**Litestream → R2** (consumed by `litestream.yml`)
- [ ] `LITESTREAM_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com`
- [ ] `LITESTREAM_BUCKET=lucre-backups`
- [ ] `LITESTREAM_ACCESS_KEY_ID=`
- [ ] `LITESTREAM_SECRET_ACCESS_KEY=`

---

## 4. Deploy  `[B10]`

The artifacts already exist: `Dockerfile` (uv + Litestream), `litestream.yml`, `docker-entrypoint.sh` (restore-on-boot, background replicate, uvicorn as PID 1). The scheduler auto-starts in the container (`LUCRE_ENABLE_SCHEDULER=1`).

- [ ] Attach a **persistent volume mounted at `/data`** on the Railway service (backup replicates to R2, but `/data` is the source of truth).
- [ ] Deploy from the `logo` branch (or `main` once PR #9 is merged).
- [ ] Confirm the healthcheck: `GET /health` → `{"status": "ok"}`.
- [ ] Open the public URL — the anonymous **intro/launch screen** should render with the "Launch demo" CTA.
- [ ] Click **Launch demo** and click through: dashboard → simulated connect → alerts preview. Confirm the "Demo — fake data" banner is present.

---

## 5. OAuth redirect URI  `[B15]`

Needed for Chase and most major banks.

- [ ] Note your deployed URL, e.g. `https://lucre.up.railway.app`.
- [ ] Register `https://<app>/link` as an allowed **redirect URI** in the Plaid dashboard.
- [ ] Set `PLAID_REDIRECT_URI=https://<app>/link` in Railway and redeploy.

---

## 6. Backup / restore drill  `[B11]`

Prove the backup actually works before you trust real data to it.

- [ ] Confirm Litestream is replicating (Railway logs should show replication, not the "R2 unreachable" fallback).
- [ ] Verify objects appear in the R2 bucket under `lucre/`.
- [ ] Run a restore drill and document the exact command in `README.md`:
  ```
  litestream restore -o /tmp/restored.db s3://<bucket>/lucre
  ```
  Open `/tmp/restored.db` and confirm data is intact.

---

## 7. Go live with real bank data  `[B12]`

Only after Plaid production is approved (step 1).

- [ ] Flip `PLAID_ENV=production` in Railway; set the production `PLAID_SECRET`. Redeploy.
- [ ] Sign in as owner (`/login`) → the real dashboard.
- [ ] Use `/link` to connect real checking / savings / credit accounts.
- [ ] Click **Sync now** and confirm real balances + transactions appear.

---

## 8. Verify alerts & email  `[G7]`

- [ ] Trigger (or wait for) the daily digest (07:30 America/New_York) — confirm it lands in Gmail.
- [ ] Trigger an urgent alert (e.g. a large transaction or low balance) — confirm it emails immediately.
- [ ] Check both render correctly **on your phone**.

---

## 9. Phone / PWA  `[B13]`

- [ ] Open the deployed URL on your phone, sign in, **Add to Home Screen**.
- [ ] Confirm the PWA opens straight to the authenticated dashboard (not the intro).
- [ ] Confirm login **survives a week** (session cookie is 1-year, but verify in practice).

---

## 10. Public exposure & showcase  `[H15 / H16 human parts]`

Code side (sitemap/robots, `noindex` on owner views, live rate limits) is done. Remaining is yours:

- [ ] Confirm the demo URL is reachable and indexable; `/login` and owner views carry `noindex`.
- [ ] Sanity-check rate limits are live (rapid demo-session creation is throttled).
- [ ] Add the deployed URL to your **resume** and **LinkedIn**.
- [ ] Confirm the résumé PDF is served on `/about` and the identity links (GitHub, LinkedIn, contact) are correct.

---

## Quick reference — what's already handled by code

- App factory, `/health`, daily sync (07:00 ET) + digest (07:30 ET) schedulers
- Argon2 login, signed session cookie, 5-attempt lockout
- Full demo isolation (per-session store, routing guard, safety sweep) — verified by tests
- Restore-on-boot + background R2 replication, timeboxed so R2 outages don't block boot
- 241 passing tests, ruff + ty clean
