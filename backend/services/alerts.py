import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from models import AlertEvent
from services.email import EmailClientLike

logger = logging.getLogger(__name__)


def record_alert(
    db: Session,
    alert_type: str,
    dedupe_key: str,
    payload: dict,
    urgency: str,
) -> AlertEvent | None:
    """Record an alert event, or return None if one with this dedupe_key exists.

    Idempotent by design: the same condition (e.g. low balance on a given day)
    re-detected on a later sync won't produce a duplicate alert."""
    if db.query(AlertEvent.id).filter_by(dedupe_key=dedupe_key).first() is not None:
        return None
    event = AlertEvent(
        type=alert_type,
        dedupe_key=dedupe_key,
        payload=json.dumps(payload),
        urgency=urgency,
    )
    db.add(event)
    db.commit()
    logger.info("Recorded %s alert (%s)", alert_type, dedupe_key)
    return event


def emit_alert(
    db: Session,
    email_client: EmailClientLike | None,
    *,
    alert_type: str,
    dedupe_key: str,
    payload: dict,
    urgency: str,
    subject: str | None = None,
    html: str | None = None,
) -> AlertEvent | None:
    """Record an alert and, if it's urgent and newly recorded, email it immediately,
    stamping emailed_at. Returns None when deduped away.

    A send failure propagates (it is logged loudly inside the client, never
    swallowed); callers that must not abort on one bad email wrap this call."""
    event = record_alert(db, alert_type, dedupe_key, payload, urgency)
    if event is None:
        return None
    if urgency == "urgent" and email_client is not None:
        if subject is None or html is None:
            raise ValueError("urgent alert requires subject and html to email")
        email_client.send(subject, html)
        event.emailed_at = datetime.now(UTC)
        db.commit()
    return event
