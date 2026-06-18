import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from services.spending import spending_by_category
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/spending")
def spending_page(request: Request, db: DbSession, month: str | None = None):
    summary = spending_by_category(db, month=month)
    max_amount = max((c.amount for c in summary.categories), default=0)
    return templates.TemplateResponse(
        request,
        "spending.html",
        {"summary": summary, "max_amount": max_amount, "month": month},
    )
