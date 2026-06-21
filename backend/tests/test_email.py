import httpx
import pytest

from models import AlertEvent
from services.alerts import emit_alert
from services.email import ResendEmailClient
from tests.conftest import FakeEmailClient


def test_emit_urgent_sends_and_stamps_emailed(db_session, fake_email):
    event = emit_alert(
        db_session,
        fake_email,
        alert_type="low_balance",
        dedupe_key="low_balance:1:2026-06-21",
        payload={"account_id": 1},
        urgency="urgent",
        subject="Low balance",
        html="<p>low</p>",
    )

    assert event is not None
    assert fake_email.sent == [("Low balance", "<p>low</p>")]
    assert event.emailed_at is not None


def test_emit_digest_does_not_send(db_session, fake_email):
    event = emit_alert(
        db_session,
        fake_email,
        alert_type="new_subscription",
        dedupe_key="new_subscription:netflix",
        payload={},
        urgency="digest",
    )

    assert event is not None
    assert fake_email.sent == []
    assert event.emailed_at is None


def test_emit_deduped_returns_none_and_does_not_send(db_session, fake_email):
    emit_alert(
        db_session,
        fake_email,
        alert_type="low_balance",
        dedupe_key="low_balance:1:2026-06-21",
        payload={},
        urgency="urgent",
        subject="s",
        html="h",
    )
    fake_email.sent.clear()

    again = emit_alert(
        db_session,
        fake_email,
        alert_type="low_balance",
        dedupe_key="low_balance:1:2026-06-21",
        payload={},
        urgency="urgent",
        subject="s",
        html="h",
    )

    assert again is None
    assert fake_email.sent == []
    assert db_session.query(AlertEvent).count() == 1


def test_urgent_without_email_client_records_only(db_session):
    event = emit_alert(
        db_session,
        None,
        alert_type="low_balance",
        dedupe_key="low_balance:1:2026-06-21",
        payload={},
        urgency="urgent",
        subject="s",
        html="h",
    )
    assert event is not None
    assert event.emailed_at is None


def test_fake_email_failure_raises(db_session):
    failing = FakeEmailClient()
    failing.fail = True
    with pytest.raises(RuntimeError):
        emit_alert(
            db_session,
            failing,
            alert_type="low_balance",
            dedupe_key="low_balance:1:2026-06-21",
            payload={},
            urgency="urgent",
            subject="s",
            html="h",
        )


def test_resend_client_posts_payload(monkeypatch, override_settings):
    override_settings(
        resend_api_key="re_test", alert_from_email="from@x.com", alert_to_email="to@x.com"
    )
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    ResendEmailClient().send("Hi", "<p>body</p>")

    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["headers"]["Authorization"] == "Bearer re_test"
    assert captured["json"] == {
        "from": "from@x.com",
        "to": ["to@x.com"],
        "subject": "Hi",
        "html": "<p>body</p>",
    }


def test_resend_client_raises_on_http_error(monkeypatch, override_settings):
    override_settings(
        resend_api_key="re_test", alert_from_email="f@x.com", alert_to_email="t@x.com"
    )

    def fake_post(url, headers, json, timeout):
        return httpx.Response(422, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(httpx.HTTPError):
        ResendEmailClient().send("Hi", "<p>body</p>")
