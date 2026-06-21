import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from models import Account
from services.settings_store import get_alert_settings
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]


def _context(db: Session) -> dict:
    cash_accounts = (
        db.query(Account).filter(Account.account_type == "depository").order_by(Account.name).all()
    )
    return {"alert_settings": get_alert_settings(db), "cash_accounts": cash_accounts}


@router.get("/settings")
def settings_page(request: Request, db: DbSession):
    return templates.TemplateResponse(request, "settings.html", _context(db))


@router.post("/settings")
async def update_settings(request: Request, db: DbSession):
    """Save the large-transaction amount and each cash account's low-balance
    threshold. A blank field clears (disables) that setting."""
    form = await request.form()
    settings = get_alert_settings(db)
    settings.large_transaction_amount = _parse_amount(form.get("large_transaction_amount"))

    for account in db.query(Account).filter(Account.account_type == "depository").all():
        settings_value = form.get(f"low_balance_threshold_{account.id}")
        account.low_balance_threshold = _parse_amount(settings_value)

    db.commit()
    logger.info("Alert settings updated")
    return RedirectResponse("/settings", status_code=303)


def _parse_amount(raw) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    return float(raw)
