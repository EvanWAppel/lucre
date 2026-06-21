"""Persist detected recurring series and raise alerts for new ones / price hikes.

Bridges the pure detector (services.recurring) to the database and alert log.
"""

import logging
from datetime import date

from sqlalchemy.orm import Session

from models import RecurringSeries, Transaction
from services.alerts import record_alert
from services.merchants import merchant_key
from services.recurring import detect_price_increase, detect_recurring

logger = logging.getLogger(__name__)

# A series is "active" if its last charge is no older than this many days (one full
# cadence plus slack); beyond that we treat it as likely cancelled.
_ACTIVE_GRACE = {"weekly": 16, "monthly": 45, "annual": 400}

# Charges per year by cadence, for annualizing cost.
_ANNUAL_MULTIPLIER = {"weekly": 52, "monthly": 12, "annual": 1}


def active_subscriptions(db: Session) -> list[RecurringSeries]:
    """Active, non-dismissed series, most expensive (annualized) first."""
    rows = db.query(RecurringSeries).filter_by(active=True, dismissed=False).all()
    rows.sort(key=lambda s: s.median_amount * _ANNUAL_MULTIPLIER[s.cadence], reverse=True)
    return rows


def annualized_total(series: list[RecurringSeries]) -> float:
    return round(sum(s.median_amount * _ANNUAL_MULTIPLIER[s.cadence] for s in series), 2)


def _spending_tuples(db: Session) -> list[tuple[str, date, float]]:
    """(merchant_key, date, amount) for outflows only (positive = money out)."""
    tuples: list[tuple[str, date, float]] = []
    for txn in db.query(Transaction).filter(Transaction.amount > 0).all():
        key = txn.merchant_key or merchant_key(txn.merchant_name or txn.name)
        if key:
            tuples.append((key, txn.date, txn.amount))
    return tuples


def sync_recurring(db: Session, today: date) -> dict:
    """Re-detect recurring series from stored transactions and reconcile the table.

    New series (not previously seen and not dismissed) raise a digest alert; a
    charge above the trailing median raises a price-increase alert. Both are
    deduped via the alert log, so re-running over the same data is a no-op."""
    detected = detect_recurring(_spending_tuples(db), today=today)
    new_count = 0

    for series in detected:
        existing = db.query(RecurringSeries).filter_by(merchant_key=series.merchant_key).first()
        grace = _ACTIVE_GRACE[series.cadence]
        is_active = (today - series.last_seen).days <= grace

        if existing is None:
            db.add(
                RecurringSeries(
                    merchant_key=series.merchant_key,
                    cadence=series.cadence,
                    median_amount=series.median_amount,
                    last_seen=series.last_seen,
                    next_expected=series.next_expected,
                    active=is_active,
                    dismissed=False,
                )
            )
            db.commit()
            new_count += 1
            record_alert(
                db,
                alert_type="new_subscription",
                dedupe_key=f"new_subscription:{series.merchant_key}",
                payload={
                    "merchant_key": series.merchant_key,
                    "cadence": series.cadence,
                    "amount": series.median_amount,
                },
                urgency="digest",
            )
        else:
            existing.cadence = series.cadence
            existing.median_amount = series.median_amount
            existing.last_seen = series.last_seen
            existing.next_expected = series.next_expected
            existing.active = is_active
            db.commit()

        # Price increase alerts fire regardless of new/existing, but only for series
        # the user hasn't dismissed. Dedupe key includes the new amount so a later,
        # larger hike still alerts.
        if existing is None or not existing.dismissed:
            increase = detect_price_increase(series)
            if increase is not None:
                record_alert(
                    db,
                    alert_type="price_increase",
                    dedupe_key=f"price_increase:{series.merchant_key}:{increase.new_amount}",
                    payload={
                        "merchant_key": series.merchant_key,
                        "old_amount": increase.old_amount,
                        "new_amount": increase.new_amount,
                    },
                    urgency="digest",
                )

    logger.info("Recurring sync: %d detected, %d new", len(detected), new_count)
    return {"detected": len(detected), "new": new_count}
