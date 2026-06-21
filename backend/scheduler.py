import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def _today_ny():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("America/New_York")).date()


def run_daily_sync() -> None:
    # Imported here so building a scheduler never drags in DB/Plaid setup.
    from database import SessionLocal
    from plaid_client import get_plaid_client
    from services.email import get_email_client
    from services.sync import run_full_sync

    logger.info("Daily sync starting")
    db = SessionLocal()
    try:
        run_full_sync(db, get_plaid_client(), _today_ny(), get_email_client())
    finally:
        db.close()


def run_daily_digest() -> None:
    from database import SessionLocal
    from services.digest import send_daily_digest
    from services.email import get_email_client

    logger.info("Daily digest starting")
    db = SessionLocal()
    try:
        send_daily_digest(db, get_email_client(), _today_ny())
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler:
    """Build (but do not start) the daily-sync scheduler.

    Started from app startup only when LUCRE_ENABLE_SCHEDULER=1, so tests and
    one-off scripts never run background jobs.
    """
    scheduler = BackgroundScheduler(timezone="America/New_York")
    scheduler.add_job(
        run_daily_sync,
        CronTrigger(hour=7, minute=0, timezone="America/New_York"),
        id="daily-sync",
    )
    scheduler.add_job(
        run_daily_digest,
        CronTrigger(hour=7, minute=30, timezone="America/New_York"),
        id="daily-digest",
    )
    return scheduler
