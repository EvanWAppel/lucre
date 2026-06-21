import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def run_daily_sync() -> None:
    # Imported here so building a scheduler never drags in DB/Plaid setup.
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from database import SessionLocal
    from plaid_client import get_plaid_client
    from services.sync import run_full_sync

    logger.info("Daily sync starting")
    today = datetime.now(ZoneInfo("America/New_York")).date()
    db = SessionLocal()
    try:
        run_full_sync(db, get_plaid_client(), today)
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
    return scheduler
