"""In-app preview of the alert emails (PRD H9).

Renders exactly what the urgent alerts and the daily digest email look like,
populated from the current data. It never sends anything — it's a showcase of the
alerting feature, reachable in the demo.
"""

import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from database import get_db
from models import AlertEvent
from services.digest import build_digest_context, render_digest
from templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/alerts/preview")
def alerts_preview(request: Request, db: DbSession):
    digest_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.urgency == "digest")
        .order_by(AlertEvent.created_at)
        .all()
    )
    urgent_events = (
        db.query(AlertEvent)
        .filter(AlertEvent.urgency == "urgent")
        .order_by(AlertEvent.created_at.desc())
        .all()
    )
    digest_html = ""
    if digest_events:
        context = build_digest_context(db, digest_events, date.today())
        digest_html = render_digest(context)
    return templates.TemplateResponse(
        request,
        "alerts_preview.html",
        {
            "digest_html": digest_html,
            "urgent_events": urgent_events,
            "has_digest": bool(digest_events),
        },
    )
