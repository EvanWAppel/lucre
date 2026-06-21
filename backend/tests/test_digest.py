from datetime import date, timedelta

from models import AlertEvent, Bill, Transaction
from services.alerts import record_alert
from services.digest import send_daily_digest
from tests.test_transactions_page import seed

TODAY = date(2026, 6, 21)


def test_digest_skips_when_no_pending_events(db_session, fake_email):
    result = send_daily_digest(db_session, fake_email, TODAY)

    assert result == {"sent": False, "events": 0}
    assert fake_email.sent == []


def test_digest_sends_and_marks_events(db_session, fake_plaid, fake_email):
    seed(db_session, fake_plaid)
    record_alert(
        db_session,
        "new_subscription",
        "new_subscription:netflix",
        {"merchant_key": "netflix", "amount": 15.49, "cadence": "monthly"},
        "digest",
    )
    record_alert(
        db_session,
        "price_increase",
        "price_increase:spotify:12.99",
        {"merchant_key": "spotify", "old_amount": 9.99, "new_amount": 12.99},
        "digest",
    )

    result = send_daily_digest(db_session, fake_email, TODAY)

    assert result["sent"] is True
    assert result["events"] == 2
    assert len(fake_email.sent) == 1
    subject, html = fake_email.sent[0]
    assert TODAY.isoformat() in subject
    assert "netflix" in html
    assert "spotify" in html
    # All pending digest events are now stamped emailed.
    assert db_session.query(AlertEvent).filter(AlertEvent.emailed_at.is_(None)).count() == 0


def test_digest_includes_yesterday_spend_and_bills(db_session, fake_plaid, fake_email):
    checking, _ = seed(db_session, fake_plaid)
    db_session.add(
        Transaction(
            account_id=checking.id,
            plaid_transaction_id="y1",
            date=TODAY - timedelta(days=1),
            name="Coffee",
            merchant_name="Coffee",
            amount=42.50,
            plaid_category="FOOD",
            pending=False,
        )
    )
    db_session.add(
        Bill(name="Rent", amount=2000.0, cadence="monthly", next_due=TODAY + timedelta(days=5))
    )
    record_alert(db_session, "bill_due_soon", "bill_due_soon:1:x", {"name": "Rent"}, "digest")
    db_session.commit()

    send_daily_digest(db_session, fake_email, TODAY)

    _, html = fake_email.sent[0]
    assert "42.50" in html
    assert "Rent" in html


def test_digest_does_not_resend_already_emailed(db_session, fake_email):
    event = record_alert(
        db_session,
        "new_subscription",
        "k",
        {"merchant_key": "x", "amount": 5.0, "cadence": "monthly"},
        "digest",
    )
    assert event is not None
    send_daily_digest(db_session, fake_email, TODAY)
    assert event.emailed_at is not None

    fake_email.sent.clear()
    result = send_daily_digest(db_session, fake_email, TODAY)

    assert result["sent"] is False
    assert fake_email.sent == []
