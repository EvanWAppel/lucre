from tests.conftest import TEST_PASSWORD
from tests.test_sync import make_item


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def seed_accounts(client, db_session) -> None:
    login(client)
    client.post(
        "/api/plaid/exchange",
        json={"public_token": "public-token-1", "institution_name": "Fake Bank"},
    )


def test_dashboard_shows_accounts_and_net_total(client, db_session):
    seed_accounts(client, db_session)
    response = client.get("/")
    assert response.status_code == 200
    assert "Everyday Checking" in response.text
    assert "Travel Card" in response.text
    assert "1,500.25" in response.text
    assert "432.10" in response.text
    # Net = 1500.25 cash − 432.10 credit
    assert "1,068.15" in response.text


def test_dashboard_empty_state_prompts_link(client, db_session):
    login(client)
    response = client.get("/")
    assert response.status_code == 200
    assert "/link" in response.text


def test_sync_now_reflects_new_balance(client, db_session, fake_plaid):
    seed_accounts(client, db_session)
    fake_plaid.accounts["access-token-1"][0]["balance"] = 1600.00

    response = client.post("/api/sync")

    assert response.status_code == 200
    assert "1,600.00" in response.text
    assert "1,500.25" not in response.text


def test_sync_now_reports_errors(client, db_session, fake_plaid):
    login(client)
    make_item(
        db_session,
        plaid_item_id="bad-item",
        access_token="missing-token",
        institution_name="Broken Bank",
    )
    response = client.post("/api/sync")
    assert response.status_code == 200
    assert "Broken Bank" in response.text
