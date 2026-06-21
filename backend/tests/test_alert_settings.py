from models import AlertSettings
from services.settings_store import get_alert_settings
from tests.conftest import TEST_PASSWORD
from tests.test_transactions_page import seed


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_get_alert_settings_creates_singleton_once(db_session):
    first = get_alert_settings(db_session)
    second = get_alert_settings(db_session)

    assert first.id == 1
    assert first is second
    assert first.large_transaction_amount is None
    assert db_session.query(AlertSettings).count() == 1


def test_settings_page_requires_login(client):
    assert client.get("/settings", follow_redirects=False).status_code == 303


def test_settings_page_renders(client, db_session, fake_plaid):
    login(client)
    seed(db_session, fake_plaid)

    response = client.get("/settings")

    assert response.status_code == 200
    assert "Everyday Checking" in response.text


def test_post_settings_saves_amounts(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)

    response = client.post(
        "/settings",
        data={
            "large_transaction_amount": "500",
            f"low_balance_threshold_{checking.id}": "100",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(checking)
    assert get_alert_settings(db_session).large_transaction_amount == 500.0
    assert checking.low_balance_threshold == 100.0


def test_post_settings_blank_clears(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    checking.low_balance_threshold = 100.0
    get_alert_settings(db_session).large_transaction_amount = 500.0
    db_session.commit()

    client.post(
        "/settings",
        data={"large_transaction_amount": "", f"low_balance_threshold_{checking.id}": ""},
        follow_redirects=False,
    )

    db_session.refresh(checking)
    assert checking.low_balance_threshold is None
    assert get_alert_settings(db_session).large_transaction_amount is None
