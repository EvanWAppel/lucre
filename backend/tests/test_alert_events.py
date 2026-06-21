from models import AlertEvent
from services.alerts import record_alert


def test_record_alert_creates_event(db_session):
    event = record_alert(
        db_session,
        alert_type="new_subscription",
        dedupe_key="new_subscription:netflix",
        payload={"merchant_key": "netflix", "amount": 15.49},
        urgency="digest",
    )
    assert event is not None
    assert event.type == "new_subscription"
    assert event.urgency == "digest"
    assert event.payload_data == {"merchant_key": "netflix", "amount": 15.49}
    assert event.created_at is not None
    assert event.emailed_at is None


def test_record_alert_dedupes_by_key(db_session):
    first = record_alert(db_session, "low_balance", "low_balance:acct-1:2026-06-17", {}, "urgent")
    second = record_alert(db_session, "low_balance", "low_balance:acct-1:2026-06-17", {}, "urgent")
    assert first is not None
    assert second is None
    assert db_session.query(AlertEvent).count() == 1


def test_different_keys_both_recorded(db_session):
    record_alert(db_session, "low_balance", "low_balance:acct-1:2026-06-17", {}, "urgent")
    record_alert(db_session, "low_balance", "low_balance:acct-1:2026-06-18", {}, "urgent")
    assert db_session.query(AlertEvent).count() == 2
