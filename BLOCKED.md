# BLOCKED — what I need from Evan

- [ ] 🔴 **Plaid production access (A8)** — apply in the Plaid dashboard; approval takes days, so start now. Until approved, everything runs in sandbox and no real bank data connects. Gates B12.
- [ ] 🔴 **Cloudflare R2 + Resend accounts (A9)** — create a Cloudflare R2 bucket + access keys (for Litestream backup/restore), a Resend account + API key (email), and have a Railway account ready.
- [ ] 🔴 **Railway persistent volume (B10)** — attach a persistent volume mounted at `/data` on the Railway service.
- [ ] 🔴 **Flip to Plaid production (B12)** — once Plaid production is approved, set `PLAID_ENV=production` in Railway env and connect real checking/savings/credit accounts via `/link`.
- [ ] 🔴 **PWA install + week-long session test (B13)** — add the PWA to your phone home screen and confirm login survives a week. On-device test only you can do.
- [ ] 🟡 **Verify real digest + alert email (G7)** — confirm a real digest and an urgent alert arrive in Gmail and look right on the phone (Resend must be configured first).
