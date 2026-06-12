import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_login
from crypto import encrypt
from database import get_db
from models import Account, Item
from plaid_client import PlaidClientLike, get_plaid_client
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]
Plaid = Annotated[PlaidClientLike, Depends(get_plaid_client)]


class ExchangeRequest(BaseModel):
    public_token: str
    institution_name: str = "Unknown institution"


@router.get("/link")
def link_page(request: Request):
    return templates.TemplateResponse(request, "link.html")


@router.post("/api/plaid/link_token")
def create_link_token(plaid: Plaid):
    return {"link_token": plaid.create_link_token()}


@router.post("/api/plaid/exchange")
def exchange(body: ExchangeRequest, db: DbSession, plaid: Plaid):
    exchanged = plaid.exchange_public_token(body.public_token)
    plaid_item_id = exchanged["item_id"]

    existing = db.query(Item).filter(Item.plaid_item_id == plaid_item_id).first()
    if existing is not None:
        raise HTTPException(
            status_code=409, detail=f"{existing.institution_name} is already connected"
        )

    item = Item(
        plaid_item_id=plaid_item_id,
        encrypted_access_token=encrypt(exchanged["access_token"]),
        institution_name=body.institution_name,
    )
    db.add(item)
    db.flush()

    accounts = plaid.get_accounts(exchanged["access_token"])
    for raw in accounts:
        account = Account(
            item_id=item.id,
            plaid_account_id=raw["plaid_account_id"],
            name=raw["name"],
            account_type=raw["type"],
            subtype=raw["subtype"],
        )
        account.touch(raw["balance"])
        db.add(account)
    db.commit()
    logger.info("Connected %s with %d accounts", body.institution_name, len(accounts))
    return {"institution": body.institution_name, "accounts": len(accounts)}
