"""Alert rules evaluated after each daily sync.

Urgent (immediate email): a cash account dipped below its low-balance threshold, or
a transaction exceeded the large-transaction amount. Digest (daily email): a bill is
due within a few days. New-subscription and price-increase digest events are raised
by services.subscriptions during the same sync.
"""

import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Account, Transaction
from services.alerts import emit_alert, record_alert
from services.bills import upcoming_bills
from services.email import EmailClientLike
from services.settings_store import get_alert_settings

logger = logging.getLogger(__name__)

# Bills due within this many days are surfaced in the digest.
_BILL_DUE_WINDOW_DAYS = 3
# Only transactions this recent are checked for the large-transaction alert, so the
# 24-month backfill doesn't flood alerts the first time a threshold is set.
_LARGE_TXN_WINDOW_DAYS = 7


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _check_low_balances(
    db: Session, email_client: EmailClientLike | None, today: date, errors: list[str]
) -> int:
    """Cash accounts below their per-account threshold raise an urgent alert,
    deduped per account per day (so re-syncing the same day won't repeat it)."""
    fired = 0
    accounts = (
        db.query(Account)
        .filter(
            Account.account_type == "depository",
            Account.low_balance_threshold.isnot(None),
            Account.balance.isnot(None),
        )
        .all()
    )
    for account in accounts:
        balance = account.balance
        threshold = account.low_balance_threshold
        if balance is None or threshold is None or balance >= threshold:
            continue
        subject = f"Low balance: {account.name}"
        html = (
            f"<p>{account.name} is at ${_money(balance)}, below your "
            f"${_money(threshold)} threshold.</p>"
        )
        try:
            event = emit_alert(
                db,
                email_client,
                alert_type="low_balance",
                dedupe_key=f"low_balance:{account.id}:{today.isoformat()}",
                payload={
                    "account_id": account.id,
                    "account_name": account.name,
                    "balance": balance,
                    "threshold": threshold,
                },
                urgency="urgent",
                subject=subject,
                html=html,
            )
            if event is not None:
                fired += 1
        except Exception:
            logger.exception("Low-balance alert failed for account %s", account.id)
            errors.append(f"low_balance:{account.id}")
    return fired


def _check_large_transactions(
    db: Session, email_client: EmailClientLike | None, today: date, errors: list[str]
) -> int:
    """Recent transactions whose absolute amount exceeds the configured limit raise
    an urgent alert, deduped per transaction (so each fires at most once)."""
    threshold = get_alert_settings(db).large_transaction_amount
    if threshold is None:
        return 0
    fired = 0
    cutoff = today - timedelta(days=_LARGE_TXN_WINDOW_DAYS)
    txns = (
        db.query(Transaction)
        .filter(Transaction.date >= cutoff, func.abs(Transaction.amount) > threshold)
        .all()
    )
    for txn in txns:
        direction = "spent" if txn.amount > 0 else "received"
        subject = f"Large transaction: ${_money(abs(txn.amount))} {txn.name}"
        html = (
            f"<p>{txn.date.isoformat()}: {direction} ${_money(abs(txn.amount))} at {txn.name}.</p>"
        )
        try:
            event = emit_alert(
                db,
                email_client,
                alert_type="large_transaction",
                dedupe_key=f"large_transaction:{txn.plaid_transaction_id}",
                payload={
                    "plaid_transaction_id": txn.plaid_transaction_id,
                    "name": txn.name,
                    "amount": txn.amount,
                    "date": txn.date.isoformat(),
                },
                urgency="urgent",
                subject=subject,
                html=html,
            )
            if event is not None:
                fired += 1
        except Exception:
            logger.exception("Large-transaction alert failed for %s", txn.plaid_transaction_id)
            errors.append(f"large_transaction:{txn.plaid_transaction_id}")
    return fired


def _check_bills_due(db: Session, today: date) -> int:
    """Bills due within the window are recorded as digest events (emailed by the
    daily digest job), deduped per bill per due date."""
    fired = 0
    for bill in upcoming_bills(db, today, days=_BILL_DUE_WINDOW_DAYS):
        event = record_alert(
            db,
            alert_type="bill_due_soon",
            dedupe_key=f"bill_due_soon:{bill.bill_id}:{bill.due.isoformat()}",
            payload={
                "bill_id": bill.bill_id,
                "name": bill.name,
                "amount": bill.amount,
                "due": bill.due.isoformat(),
            },
            urgency="digest",
        )
        if event is not None:
            fired += 1
    return fired


def run_post_sync_alerts(db: Session, email_client: EmailClientLike | None, today: date) -> dict:
    """Evaluate every post-sync rule. One failing alert is logged and reported, never
    aborting the rest."""
    errors: list[str] = []
    low_balance = _check_low_balances(db, email_client, today, errors)
    large_transaction = _check_large_transactions(db, email_client, today, errors)
    bills_due = _check_bills_due(db, today)
    logger.info(
        "Post-sync alerts: %d low-balance, %d large-txn, %d bills-due, %d errors",
        low_balance,
        large_transaction,
        bills_due,
        len(errors),
    )
    return {
        "low_balance": low_balance,
        "large_transaction": large_transaction,
        "bills_due": bills_due,
        "errors": errors,
    }
