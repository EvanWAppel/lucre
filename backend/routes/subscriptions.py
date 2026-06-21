import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth import require_login
from database import get_db
from models import RecurringSeries
from services.subscriptions import active_subscriptions, annualized_total
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_login)])

DbSession = Annotated[Session, Depends(get_db)]


def _context(db: Session) -> dict:
    subs = active_subscriptions(db)
    return {"subscriptions": subs, "annual_total": annualized_total(subs)}


@router.get("/subscriptions")
def subscriptions_page(request: Request, db: DbSession):
    return templates.TemplateResponse(request, "subscriptions.html", _context(db))


@router.post("/api/subscriptions/{series_id}/dismiss")
def dismiss(request: Request, series_id: int, db: DbSession):
    series = db.get(RecurringSeries, series_id)
    if series is None:
        raise HTTPException(status_code=404, detail="Subscription not found")
    series.dismissed = True
    db.commit()
    logger.info("Dismissed subscription %s (%s)", series_id, series.merchant_key)
    return templates.TemplateResponse(request, "_subscriptions_list.html", _context(db))
