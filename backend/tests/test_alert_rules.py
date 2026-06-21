from datetime import date, timedelta

from models import AlertEvent, Bill, Transaction
from services.alert_rules import run_post_sync_alerts
from services.settings_store import get_alert_settings
from tests.test_transactions_page import seed

TODAY = date(2026, 6, 21)


def add_txn(db_session, account, tid, amount, when=TODAY):
    txn = Transaction(
        account_id=account.id,
        plaid_transaction_id=tid,
        date=when,
        name=f"txn-{tid}",
        merchant_name=f"txn-{tid}",
        amount=amount,
        plaid_category="GENERAL",
        pending=False,
    )
    db_session.add(txn)
    db_session.commit()
    return txn


# --- low balance (G3) ---


def test_low_balance_fires_urgent_and_emails(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)  # checking balance 1500.25
    checking.low_balance_threshold = 2000.0
    db_session.commit()

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["low_balance"] == 1
    event = db_session.query(AlertEvent).filter_by(type="low_balance").one()
    assert event.urgency == "urgent"
    assert event.emailed_at is not None
    assert len(fake_email.sent) == 1


def test_low_balance_respects_threshold(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    checking.low_balance_threshold = 1000.0  # balance 1500.25 is above
    db_session.commit()

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["low_balance"] == 0
    assert db_session.query(AlertEvent).filter_by(type="low_balance").count() == 0


def test_low_balance_dedupes_within_day(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    checking.low_balance_threshold = 2000.0
    db_session.commit()

    run_post_sync_alerts(db_session, fake_email, TODAY)
    run_post_sync_alerts(db_session, fake_email, TODAY)  # same day, no repeat

    assert db_session.query(AlertEvent).filter_by(type="low_balance").count() == 1
    assert len(fake_email.sent) == 1


def test_low_balance_realerts_next_day(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    checking.low_balance_threshold = 2000.0
    db_session.commit()

    run_post_sync_alerts(db_session, fake_email, TODAY)
    run_post_sync_alerts(db_session, fake_email, TODAY + timedelta(days=1))

    assert db_session.query(AlertEvent).filter_by(type="low_balance").count() == 2


def test_low_balance_ignores_credit_accounts(db_session, fake_plaid, fake_email):
    _, credit = seed(db_session, fake_plaid)
    credit.low_balance_threshold = 10000.0  # nonsensical, must be ignored
    db_session.commit()

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["low_balance"] == 0


# --- large transaction (G3) ---


def test_large_transaction_fires_on_abs_amount(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    get_alert_settings(db_session).large_transaction_amount = 100.0
    db_session.commit()
    add_txn(db_session, checking, "spend-big", 250.0)
    add_txn(db_session, checking, "deposit-big", -300.0)  # abs > threshold too
    add_txn(db_session, checking, "small", 20.0)

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["large_transaction"] == 2
    assert len(fake_email.sent) == 2


def test_large_transaction_disabled_when_threshold_none(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "spend-big", 9999.0)

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["large_transaction"] == 0


def test_large_transaction_dedupes_per_txn(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    get_alert_settings(db_session).large_transaction_amount = 100.0
    db_session.commit()
    add_txn(db_session, checking, "spend-big", 250.0)

    run_post_sync_alerts(db_session, fake_email, TODAY)
    run_post_sync_alerts(db_session, fake_email, TODAY)

    assert db_session.query(AlertEvent).filter_by(type="large_transaction").count() == 1


def test_large_transaction_ignores_old_transactions(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    get_alert_settings(db_session).large_transaction_amount = 100.0
    db_session.commit()
    add_txn(db_session, checking, "old-big", 250.0, when=TODAY - timedelta(days=30))

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["large_transaction"] == 0


# --- bills due digest (G4) ---


def test_bill_due_within_window_records_digest(db_session, fake_plaid, fake_email):
    seed(db_session, fake_plaid)
    db_session.add(
        Bill(name="Rent", amount=2000.0, cadence="monthly", next_due=TODAY + timedelta(days=2))
    )
    db_session.commit()

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["bills_due"] == 1
    event = db_session.query(AlertEvent).filter_by(type="bill_due_soon").one()
    assert event.urgency == "digest"
    assert event.emailed_at is None  # digest, not emailed immediately
    assert event.payload_data["name"] == "Rent"


def test_bill_beyond_window_not_recorded(db_session, fake_plaid, fake_email):
    seed(db_session, fake_plaid)
    db_session.add(
        Bill(name="Rent", amount=2000.0, cadence="monthly", next_due=TODAY + timedelta(days=10))
    )
    db_session.commit()

    result = run_post_sync_alerts(db_session, fake_email, TODAY)

    assert result["bills_due"] == 0
