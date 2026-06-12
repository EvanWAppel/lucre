import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from models import Account
from plaid_client import PlaidClientLike, get_plaid_client
from services.sync import sync_balances
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])


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


@router.get("/")
def index(request: Request, db: DbSession):
    return templates.TemplateResponse(request, "dashboard.html", dashboard_context(db))


@router.post("/api/sync")
def sync_now(request: Request, db: DbSession, plaid: Plaid):
    result = sync_balances(db, plaid)
    return templates.TemplateResponse(
        request, "_accounts.html", dashboard_context(db, sync_errors=result["errors"])
    )
