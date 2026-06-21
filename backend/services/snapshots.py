import logging
from datetime import date

from sqlalchemy.orm import Session

from models import Account, BalanceSnapshot

logger = logging.getLogger(__name__)


def write_snapshots(db: Session, today: date) -> int:
    """Record today's balance for every account with a known balance. Idempotent:
    re-running the same day updates the existing row rather than duplicating."""
    count = 0
    for account in db.query(Account).all():
        if account.balance is None:
            continue
        snap = db.query(BalanceSnapshot).filter_by(account_id=account.id, date=today).first()
        if snap is None:
            snap = BalanceSnapshot(account_id=account.id, date=today, balance=account.balance)
            db.add(snap)
        else:
            snap.balance = account.balance
        count += 1
    db.commit()
    logger.info("Wrote %d balance snapshots for %s", count, today)
    return count
