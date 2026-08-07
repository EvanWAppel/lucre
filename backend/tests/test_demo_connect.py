from models import Account
from plaid_client import get_plaid_client
from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_connect_page_lists_banks_for_demo(client):
    response = client.get("/demo/connect")
    assert response.status_code == 200
    assert "Chase" in response.text
    assert "simulated" in response.text.lower()


def test_connecting_adds_account_to_sandbox(client, db_session):
    response = client.post("/demo/connect", data={"institution": "Chase"}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    names = {a.name for a in db_session.query(Account).all()}
    assert "Chase Checking" in names


def test_connect_never_calls_plaid(client):
    """Even if Plaid would explode, the simulated connect must work."""

    class ExplodingPlaid:
        def __getattr__(self, _name):
            raise AssertionError("demo connect must not call Plaid")

    from main import app

    # The client fixture clears all overrides at teardown.
    app.dependency_overrides[get_plaid_client] = lambda: ExplodingPlaid()
    response = client.post(
        "/demo/connect", data={"institution": "Ally Bank"}, follow_redirects=False
    )
    assert response.status_code == 303


def test_owner_is_sent_to_real_link(client):
    login(client)
    response = client.get("/demo/connect", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/link"
