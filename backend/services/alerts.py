import json
import logging

from sqlalchemy.orm import Session

from models import AlertEvent

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
