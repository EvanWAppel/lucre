import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from models import Account, Transaction
from services.merchants import merchant_key
from services.rules import apply_rule_to_existing, delete_rule, upsert_rule
from services.transactions import distinct_categories, query_transactions
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/transactions")
def transactions_page(
    request: Request,
    db: DbSession,
    month: str | None = None,
    account_id: int | None = None,
    category: str | None = None,
    page: int = 1,
):
    result = query_transactions(
        db, month=month, account_id=account_id, category=category, page=page
    )
    context = {
        "result": result,
        "accounts": db.query(Account).order_by(Account.name).all(),
        "categories": distinct_categories(db),
        "filters": {"month": month, "account_id": account_id, "category": category},
    }
    # HTMX requests for the next page get just the rows fragment to append.
    template = (
        "_transaction_rows.html" if request.headers.get("HX-Request") else "transactions.html"
    )
    return templates.TemplateResponse(request, template, context)


@router.patch("/api/transactions/{transaction_id}/category")
def recategorize(
    request: Request,
    transaction_id: int,
    db: DbSession,
    category: Annotated[str, Form()] = "",
    apply_to_merchant: Annotated[bool, Form()] = False,
):
    txn = db.get(Transaction, transaction_id)
    if txn is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    new_category = category.strip() or None
    # Blank clears the override and falls back to Plaid's category.
    txn.user_category = new_category
    db.commit()

    if apply_to_merchant:
        key = txn.merchant_key or merchant_key(txn.merchant_name or txn.name)
        if new_category:
            upsert_rule(db, key, new_category)
            apply_rule_to_existing(db, key, new_category)
        else:
            delete_rule(db, key)

    db.refresh(txn)
    logger.info("Recategorized transaction %s -> %s", transaction_id, txn.effective_category)
    return templates.TemplateResponse(
        request, "_category_cell.html", {"txn": txn, "categories": distinct_categories(db)}
    )
