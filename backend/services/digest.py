"""The daily digest email: a morning summary built from un-emailed digest alert
events plus live context (yesterday's spend, current balances, upcoming bills)."""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Account, AlertEvent, Transaction
from services.bills import upcoming_bills
from services.email import EmailClientLike
from templating import templates

logger = logging.getLogger(__name__)


@dataclass
class DigestContext:
    events: list[AlertEvent]
    new_subscriptions: list[AlertEvent]
    price_increases: list[AlertEvent]
    bills_due: list[AlertEvent]
    yesterday_spend: float
    upcoming: list
    cash_total: float
    credit_total: float
    net_total: float


def _pending_digest_events(db: Session) -> list[AlertEvent]:
    return (
        db.query(AlertEvent)
        .filter(AlertEvent.urgency == "digest", AlertEvent.emailed_at.is_(None))
        .order_by(AlertEvent.created_at)
        .all()
    )


def _yesterday_spend(db: Session, today: date) -> float:
    yesterday = today - timedelta(days=1)
    total = (
        db.query(func.sum(Transaction.amount))
        .filter(Transaction.date == yesterday, Transaction.amount > 0)
        .scalar()
    )
    return round(total or 0.0, 2)


def build_digest_context(db: Session, events: list[AlertEvent], today: date) -> DigestContext:
    accounts = db.query(Account).all()
    cash_total = sum(a.balance or 0 for a in accounts if a.account_type == "depository")
    credit_total = sum(a.balance or 0 for a in accounts if a.account_type == "credit")
    return DigestContext(
        events=events,
        new_subscriptions=[e for e in events if e.type == "new_subscription"],
        price_increases=[e for e in events if e.type == "price_increase"],
        bills_due=[e for e in events if e.type == "bill_due_soon"],
        yesterday_spend=_yesterday_spend(db, today),
        upcoming=upcoming_bills(db, today),
        cash_total=cash_total,
        credit_total=credit_total,
        net_total=cash_total - credit_total,
    )


def render_digest(context: DigestContext) -> str:
    return templates.env.get_template("email/digest.html").render(ctx=context)


def send_daily_digest(db: Session, email_client: EmailClientLike, today: date) -> dict:
    """Render and send the digest from un-emailed digest events, then mark them
    emailed. Skips sending entirely when there are no pending digest events."""
    events = _pending_digest_events(db)
    if not events:
        logger.info("Daily digest: nothing pending, skipping")
        return {"sent": False, "events": 0}

    context = build_digest_context(db, events, today)
    html = render_digest(context)
    email_client.send(f"Lucre daily digest — {today.isoformat()}", html)

    now = datetime.now(UTC)
    for event in events:
        event.emailed_at = now
    db.commit()
    logger.info("Daily digest: sent, marked %d events emailed", len(events))
    return {"sent": True, "events": len(events)}
