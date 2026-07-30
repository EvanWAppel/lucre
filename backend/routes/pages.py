import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from auth import SessionRole, current_role, require_login
from database import get_db
from models import Account
from plaid_client import PlaidClientLike, get_plaid_client
from services.sync import sync_balances
from templating import templates

logger = logging.getLogger(__name__)

# Open to both roles: owner sees real data, demo sees its sandbox (get_db routes it).
router = APIRouter()


def dashboard_context(db: Session, sync_errors: list[str] | None = None) -> dict:
    accounts = db.query(Account).order_by(Account.account_type, Account.name).all()
    cash_accounts = [a for a in accounts if a.account_type == "depository"]
    credit_accounts = [a for a in accounts if a.account_type == "credit"]
    cash_total = sum(a.balance or 0 for a in cash_accounts)
    credit_total = sum(a.balance or 0 for a in credit_accounts)
    refresh_times = [a.last_refreshed_at for a in accounts if a.last_refreshed_at is not None]
    return {
        "cash_accounts": cash_accounts,
        "credit_accounts": credit_accounts,
        "cash_total": cash_total,
        "credit_total": credit_total,
        "net_total": cash_total - credit_total,
        "last_refreshed_at": max(refresh_times) if refresh_times else None,
        "sync_errors": sync_errors or [],
    }


DbSession = Annotated[Session, Depends(get_db)]
Plaid = Annotated[PlaidClientLike, Depends(get_plaid_client)]
Role = Annotated[SessionRole, Depends(current_role)]


@router.get("/")
def index(request: Request, role: Role):
    """Owner lands on the dashboard; an anonymous visitor sees the intro/launch
    screen. The intro takes no DB session, so merely visiting the root never spins
    up a demo sandbox — that happens when they click into the app."""
    if role is SessionRole.OWNER:
        return RedirectResponse("/dashboard", status_code=303)
    return templates.TemplateResponse(request, "intro.html", {"hide_banner": True})


@router.get("/dashboard")
def dashboard(request: Request, db: DbSession):
    return templates.TemplateResponse(request, "dashboard.html", dashboard_context(db))


@router.get("/about")
def about(request: Request):
    """Public engineering story + identity. Reachable by anyone (no DB needed)."""
    return templates.TemplateResponse(request, "about.html")


_ROBOTS = """User-agent: *
Allow: /$
Allow: /about
Disallow: /login
Disallow: /dashboard
Disallow: /transactions
Disallow: /spending
Disallow: /subscriptions
Disallow: /bills
Disallow: /settings
Disallow: /alerts
Disallow: /demo
Disallow: /api
"""


@router.get("/robots.txt")
def robots() -> PlainTextResponse:
    """Index the intro + About; keep crawlers off login, owner views, and the
    per-visitor app routes (so bots don't spin up demo sandboxes)."""
    return PlainTextResponse(_ROBOTS)


@router.post("/api/sync", dependencies=[Depends(require_login)])
def sync_now(request: Request, db: DbSession, plaid: Plaid):
    """Owner-only: a real Plaid balance refresh. The demo uses the simulated
    connect flow instead (it never calls Plaid)."""
    result = sync_balances(db, plaid)
    return templates.TemplateResponse(
        request, "_accounts.html", dashboard_context(db, sync_errors=result["errors"])
    )
