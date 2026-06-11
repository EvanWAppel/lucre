# Lucre

Personal finance PWA — all your bank and credit card balances in one place.

## Stack

- **Frontend**: Next.js 14 (App Router) + Tailwind CSS — deployed as a PWA
- **Backend**: Python FastAPI — serves Plaid API routes and caches balances
- **Database**: PostgreSQL (Railway managed)
- **Bank data**: [Plaid](https://plaid.com) Development environment
- **Hosting**: [Railway](https://railway.app) (monorepo, two services)

## Project Structure

```
lucre/
  frontend/   # Next.js PWA
  backend/    # Python FastAPI
  railway.toml
```

## Getting Started

### Prerequisites

- [uv](https://docs.astral.sh/uv/) — Python package manager
- Node.js 18+ and npm
- A [Plaid](https://dashboard.plaid.com) account (Development environment)
- A PostgreSQL database

### 1. Clone and configure

```bash
git clone <repo>
cd lucre
cp .env.example .env
# Fill in PLAID_CLIENT_ID, PLAID_SECRET, DATABASE_URL, ENCRYPTION_KEY
```

### 2. Backend

```bash
cd backend
uv sync
uv run python -m pytest       # run tests
uv run uvicorn main:app --reload --port 8000
```

### 3. Frontend

```bash
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

### 4. Open on phone

With both servers running on your local network, open the Railway-deployed URL on your phone and add it to your home screen.

## Environment Variables

See [`.env.example`](.env.example) for all required variables.

## Deployment (Railway)

Push to your linked GitHub repo. Railway auto-deploys both services from `railway.toml`.
Set the environment variables in the Railway dashboard for each service.
