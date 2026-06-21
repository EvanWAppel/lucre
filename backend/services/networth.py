import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import Account, BalanceSnapshot

logger = logging.getLogger(__name__)


def sparkline_points(
    values: list[float], width: float = 300, height: float = 60
) -> list[tuple[float, float]]:
    """Map a value series to (x, y) coords in a width×height box. Higher values sit
    higher (smaller y); a flat series sits on the midline."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [(0.0, round(height / 2, 2))]

    lo, hi = min(values), max(values)
    span = hi - lo
    points = []
    for i, v in enumerate(values):
        x = round(i / (n - 1) * width, 2)
        y = round(height / 2 if span == 0 else height - (v - lo) / span * height, 2)
        points.append((x, y))
    return points


def networth_series(db: Session, start: date, end: date) -> list[tuple[date, float]]:
    """Daily net worth (cash − credit) from start to end inclusive.

    Each account carries its most recent snapshot forward to days it has none. A
    day appears only once at least one account has a snapshot on or before it, so
    leading days before any data are omitted."""
    snaps_by_account: dict[int, tuple[Account, list[tuple[date, float]]]] = {}
    for account in db.query(Account).all():
        rows = (
            db.query(BalanceSnapshot)
            .filter_by(account_id=account.id)
            .order_by(BalanceSnapshot.date)
            .all()
        )
        if rows:
            snaps_by_account[account.id] = (account, [(r.date, r.balance) for r in rows])

    series: list[tuple[date, float]] = []
    day = start
    while day <= end:
        total = 0.0
        has_data = False
        for account, rows in snaps_by_account.values():
            balance = None
            for snap_date, snap_balance in rows:
                if snap_date <= day:
                    balance = snap_balance
                else:
                    break
            if balance is not None:
                has_data = True
                sign = -1 if account.account_type == "credit" else 1
                total += sign * balance
        if has_data:
            series.append((day, round(total, 2)))
        day += timedelta(days=1)

    return series
