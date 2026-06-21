from datetime import date, timedelta

from models import AlertEvent, RecurringSeries, Transaction
from services.subscriptions import sync_recurring
from tests.test_transactions_page import seed


def add_monthly_charges(db_session, account, key_name, amounts, start=date(2025, 1, 5)):
    """Insert monthly outflow transactions for one merchant."""
    for i, amt in enumerate(amounts):
        txn = Transaction(
            account_id=account.id,
            plaid_transaction_id=f"{key_name}-{i}",
            date=start + timedelta(days=30 * i),
            name=key_name.upper(),
            merchant_name=key_name.title(),
            amount=amt,
            plaid_category="GENERAL_SERVICES",
            pending=False,
        )
        db_session.add(txn)
    db_session.commit()


def test_detected_series_persisted(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_monthly_charges(db_session, checking, "netflix", [15.49] * 6)

    sync_recurring(db_session, today=date(2025, 7, 1))

    series = db_session.query(RecurringSeries).all()
    assert len(series) == 1
    assert series[0].merchant_key == "netflix"
    assert series[0].cadence == "monthly"
    assert series[0].median_amount == 15.49
    assert series[0].active is True
    assert series[0].dismissed is False


def test_new_series_records_one_alert_not_repeated(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_monthly_charges(db_session, checking, "netflix", [15.49] * 6)

    sync_recurring(db_session, today=date(2025, 7, 1))
    sync_recurring(db_session, today=date(2025, 7, 2))  # re-run, same data

    alerts = db_session.query(AlertEvent).filter_by(type="new_subscription").all()
    assert len(alerts) == 1
    assert alerts[0].payload_data["merchant_key"] == "netflix"
    assert alerts[0].urgency == "digest"
    # And only one series row.
    assert db_session.query(RecurringSeries).count() == 1


def test_price_increase_recorded(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_monthly_charges(db_session, checking, "netflix", [15.49, 15.49, 15.49, 16.99])

    sync_recurring(db_session, today=date(2025, 6, 1))

    increase = db_session.query(AlertEvent).filter_by(type="price_increase").one()
    assert increase.payload_data["old_amount"] == 15.49
    assert increase.payload_data["new_amount"] == 16.99


def test_dismissed_series_not_realerted(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_monthly_charges(db_session, checking, "netflix", [15.49] * 6)
    sync_recurring(db_session, today=date(2025, 7, 1))

    series = db_session.query(RecurringSeries).one()
    series.dismissed = True
    db_session.commit()
    db_session.query(AlertEvent).delete()
    db_session.commit()

    sync_recurring(db_session, today=date(2025, 7, 2))

    assert db_session.query(RecurringSeries).filter_by(dismissed=True).count() == 1
    assert db_session.query(AlertEvent).filter_by(type="new_subscription").count() == 0
