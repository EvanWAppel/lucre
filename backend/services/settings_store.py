"""Access to the AlertSettings singleton row."""

import logging

from sqlalchemy.orm import Session

from models import AlertSettings

logger = logging.getLogger(__name__)

_SINGLETON_ID = 1


def get_alert_settings(db: Session) -> AlertSettings:
    """Return the singleton AlertSettings row, creating it (with alerts disabled)
    on first access."""
    settings = db.get(AlertSettings, _SINGLETON_ID)
    if settings is None:
        settings = AlertSettings(id=_SINGLETON_ID, large_transaction_amount=None)
        db.add(settings)
        db.commit()
        logger.info("Created AlertSettings singleton")
    return settings
