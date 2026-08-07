"""Simulated bank-connect flow for demo visitors (PRD H8).

Looks like connecting a bank, but it never calls Plaid: it just inserts a new
institution + account + a few transactions into the visitor's sandboxed demo
store. Owners are sent to the real Plaid Link flow instead.
"""

import logging
import secrets
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from auth import SessionRole, current_role
from database import get_db
from models import Account, Item, Transaction
from services.merchants import merchant_key as compute_merchant_key
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]
Role = Annotated[SessionRole, Depends(current_role)]

_DEMO_BANKS = ["Chase", "Bank of America", "Wells Fargo", "Ally Bank", "Capital One"]

# A few recent transactions seeded onto the newly "connected" account.
_SAMPLE_TXNS = [
    ("WHOLE FOODS MKT", "Whole Foods", "FOOD_AND_DRINK", 64.20),
    ("SHELL OIL 5567", "Shell", "TRANSPORTATION", 41.10),
    ("AMAZON MKTP US", "Amazon", "GENERAL_MERCHANDISE", 27.99),
]


@router.get("/demo/connect")
def connect_page(request: Request, role: Role):
    if role is SessionRole.OWNER:
        return RedirectResponse("/link", status_code=303)
    return templates.TemplateResponse(
        request, "demo_connect.html", {"banks": _DEMO_BANKS, "hide_banner": True}
    )


@router.post("/demo/connect")
def connect_submit(
    request: Request, db: DbSession, role: Role, institution: Annotated[str, Form()]
):
    if role is SessionRole.OWNER:
        return RedirectResponse("/link", status_code=303)
    _add_demo_institution(db, institution)
    return RedirectResponse("/dashboard", status_code=303)


def _add_demo_institution(db: Session, institution: str) -> None:
    """Insert a fake institution + checking account + a few transactions. No Plaid."""
    token = secrets.token_hex(3)
    slug = institution.lower().replace(" ", "-")
    item = Item(
        plaid_item_id=f"demo-connect-{slug}-{token}",
        encrypted_access_token="demo",
        institution_name=institution,
    )
    db.add(item)
    db.flush()
    account = Account(
        item_id=item.id,
        plaid_account_id=f"demo-connect-{slug}-{token}-chk",
        name=f"{institution} Checking",
        account_type="depository",
        subtype="checking",
        balance=2438.55,
    )
    db.add(account)
    db.flush()
    today = date.today()
    for i, (name, merchant, category, amount) in enumerate(_SAMPLE_TXNS):
        db.add(
            Transaction(
                account_id=account.id,
                plaid_transaction_id=f"demo-connect-{slug}-{token}-{i}",
                date=today - timedelta(days=i + 1),
                name=name,
                merchant_name=merchant,
                amount=amount,
                plaid_category=category,
                merchant_key=compute_merchant_key(merchant),
                pending=False,
            )
        )
    db.commit()
    logger.info("Demo institution connected (simulated): %s", institution)
