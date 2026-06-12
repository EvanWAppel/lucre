from crypto import decrypt
from models import Account, Item
from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_link_page_requires_login(client):
    response = client.get("/link", follow_redirects=False)
    assert response.status_code == 303


def test_link_page_renders(client):
    login(client)
    response = client.get("/link")
    assert response.status_code == 200
    assert "Plaid" in response.text


def test_link_token_endpoint(client):
    login(client)
    response = client.post("/api/plaid/link_token")
    assert response.status_code == 200
    assert response.json() == {"link_token": "link-sandbox-fake-token"}


def test_exchange_persists_item_and_accounts(client, db_session):
    login(client)
    response = client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-token-1", "institution_name": "Fake Bank"},
    )
    assert response.status_code == 200, response.text

    item = db_session.query(Item).one()
    assert item.plaid_item_id == "plaid-item-1"
    assert item.institution_name == "Fake Bank"
    # Stored encrypted, decrypts back to the real access token.
    assert item.encrypted_access_token != "access-token-1"
    assert decrypt(item.encrypted_access_token) == "access-token-1"

    accounts = db_session.query(Account).order_by(Account.plaid_account_id).all()
    assert [a.plaid_account_id for a in accounts] == ["acct-checking-1", "acct-credit-1"]
    assert accounts[0].balance == 1500.25
    assert accounts[0].last_refreshed_at is not None


def test_duplicate_exchange_rejected(client, db_session):
    login(client)
    body = {"public_token": "public-token-1", "institution_name": "Fake Bank"}
    assert client.post("/api/plaid/exchange", json=body).status_code == 200
    response = client.post("/api/plaid/exchange", json=body)
    assert response.status_code == 409
    assert db_session.query(Item).count() == 1
