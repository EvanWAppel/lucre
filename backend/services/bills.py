"""Bills calendar: derive bills from recurring series, predict due dates, and
list what's due soon.

Due-date prediction is a pure function so the month-boundary edge cases (a bill
due on the 31st in a 30-day month, February) are easy to test exhaustively.
"""

import calendar
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from models import Bill, RecurringSeries

logger = logging.getLogger(__name__)

# Roughly one cadence period in days, for advancing a due date toward today.
_CADENCE_DAYS = {"weekly": 7, "monthly": 30, "annual": 365}


def _clamp_day(year: int, month: int, day: int) -> date:
    """The given day-of-month, clamped to the month's length (Feb 31 -> Feb 28/29)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))


def _add_months(d: date, n: int, *, day: int | None = None) -> date:
    total = (d.month - 1) + n
    year = d.year + total // 12
    month = total % 12 + 1
    return _clamp_day(year, month, day if day is not None else d.day)


def _advance(d: date, cadence: str) -> date:
    if cadence == "weekly":
        return d + timedelta(days=7)
    if cadence == "monthly":
        return _add_months(d, 1)
    if cadence == "annual":
        return _add_months(d, 12)
    raise ValueError(f"Unknown cadence: {cadence}")


def predict_due_date(
    cadence: str | None,
    base_due: date | None,
    due_day_override: int | None,
    today: date,
) -> date | None:
    """The next due date on/after `today`.

    A monthly `due_day_override` pins the bill to that day-of-month, clamped to
    the month's length. Otherwise the anchor (`base_due`) is rolled forward one
    cadence at a time until it reaches today.
    """
    if cadence == "monthly" and due_day_override is not None:
        candidate = _clamp_day(today.year, today.month, due_day_override)
        if candidate < today:
            candidate = _add_months(today, 1, day=due_day_override)
        return candidate

    if cadence is None or base_due is None:
        return None

    due = base_due
    guard = 0
    while due < today and guard < 600:
        due = _advance(due, cadence)
        guard += 1
    return due


def bill_due_date(bill: Bill, today: date) -> date | None:
    return predict_due_date(bill.effective_cadence, bill.base_due, bill.due_day_override, today)


def seed_derived_bills(db: Session, today: date) -> dict:
    """Reconcile derived bills with the active recurring series.

    Each active, non-dismissed series gets exactly one derived bill; a series that
    becomes inactive or is dismissed has its derived bill removed (this is how
    dismissing a subscription hides its bill). Manual bills are never touched.
    Idempotent: re-running over the same series set is a no-op.
    """
    existing = {
        bill.recurring_series_id: bill
        for bill in db.query(Bill).filter(Bill.recurring_series_id.isnot(None)).all()
    }
    active = db.query(RecurringSeries).filter_by(active=True, dismissed=False).all()
    active_ids = {series.id for series in active}

    created = removed = 0
    for series in active:
        if series.id not in existing:
            db.add(Bill(recurring_series_id=series.id))
            created += 1
    for series_id, bill in existing.items():
        if series_id not in active_ids:
            db.delete(bill)
            removed += 1

    db.commit()
    logger.info("Derived bills: %d created, %d removed", created, removed)
    return {"created": created, "removed": removed}


@dataclass
class UpcomingBill:
    bill_id: int
    due: date
    name: str
    amount: float | None
    cadence: str | None
    source: str  # derived | manual
    autopay: bool
    is_derived: bool


def upcoming_bills(db: Session, today: date, days: int = 30) -> list[UpcomingBill]:
    """Bills due within `days` of `today`, soonest first.

    Derived bills whose series has since been dismissed or gone inactive are
    skipped even if a stale row lingers (sync prunes them, but the view shouldn't
    wait for the next sync)."""
    horizon = today + timedelta(days=days)
    items: list[UpcomingBill] = []
    for bill in db.query(Bill).all():
        if bill.is_derived and (
            bill.series is None or not bill.series.active or bill.series.dismissed
        ):
            continue
        due = bill_due_date(bill, today)
        if due is None or due < today or due > horizon:
            continue
        items.append(
            UpcomingBill(
                bill_id=bill.id,
                due=due,
                name=bill.effective_name,
                amount=bill.effective_amount,
                cadence=bill.effective_cadence,
                source=bill.source,
                autopay=bill.autopay,
                is_derived=bill.is_derived,
            )
        )
    items.sort(key=lambda b: b.due)
    return items


def upcoming_total(items: list[UpcomingBill]) -> float:
    return round(sum(b.amount for b in items if b.amount is not None), 2)
