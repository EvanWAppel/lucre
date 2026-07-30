from datetime import date

from services.demo_seed import seed_demo_data

TODAY = date(2026, 6, 28)


def test_preview_open_to_demo(client):
    assert client.get("/alerts/preview", follow_redirects=False).status_code == 200


def test_preview_renders_urgent_and_digest(client, db_session):
    seed_demo_data(db_session, TODAY)
    response = client.get("/alerts/preview")
    assert response.status_code == 200
    # Urgent alert cards
    assert "Low balance" in response.text
    assert "Large transaction" in response.text
    # Digest email rendered into an isolated iframe
    assert "srcdoc" in response.text
    assert "daily digest" in response.text.lower()


def test_preview_never_sends_email(client, db_session, fake_email):
    seed_demo_data(db_session, TODAY)
    client.get("/alerts/preview")
    assert fake_email.sent == []  # previewing must not send anything
