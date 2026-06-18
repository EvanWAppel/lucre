from services.spending import spending_by_category
from tests.conftest import TEST_PASSWORD
from tests.test_transactions_page import add_txn, seed


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_spending_sums_by_effective_category(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "a", 3, "REST A", 40.0, plaid_cat="FOOD_AND_DRINK", month=5)
    add_txn(db_session, checking, "b", 4, "REST B", 60.0, plaid_cat="FOOD_AND_DRINK", month=5)
    add_txn(db_session, checking, "c", 5, "SHOP", 30.0, plaid_cat="GENERAL_MERCHANDISE", month=5)

    summary = spending_by_category(db_session, month="2026-05")

    assert summary.total == 130.0
    assert summary.categories[0].name == "FOOD_AND_DRINK"
    assert summary.categories[0].amount == 100.0
    assert summary.categories[1].name == "GENERAL_MERCHANDISE"
    assert summary.categories[1].amount == 30.0


def test_spending_honors_user_category(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(
        db_session,
        checking,
        "a",
        3,
        "COSTCO",
        200.0,
        plaid_cat="GENERAL_MERCHANDISE",
        user_cat="Groceries",
        month=5,
    )

    summary = spending_by_category(db_session, month="2026-05")

    assert summary.categories[0].name == "Groceries"
    assert summary.categories[0].amount == 200.0


def test_spending_excludes_refunds_from_spend_but_nets_category(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    # Plaid sign convention: positive = money out, negative = money in (refund).
    add_txn(
        db_session, checking, "buy", 3, "STORE", 100.0, plaid_cat="GENERAL_MERCHANDISE", month=5
    )
    add_txn(
        db_session, checking, "refund", 4, "STORE", -30.0, plaid_cat="GENERAL_MERCHANDISE", month=5
    )

    summary = spending_by_category(db_session, month="2026-05")

    # Net spend in the category is 70; total spend is 70.
    assert summary.total == 70.0
    assert summary.categories[0].amount == 70.0


def test_spending_filters_by_month(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "may", 3, "A", 10.0, plaid_cat="X", month=5)
    add_txn(db_session, checking, "jun", 3, "B", 99.0, plaid_cat="X", month=6)

    summary = spending_by_category(db_session, month="2026-05")

    assert summary.total == 10.0


def test_spending_page_requires_login(client):
    assert client.get("/spending", follow_redirects=False).status_code == 303


def test_spending_page_renders(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "a", 3, "REST", 40.0, plaid_cat="FOOD_AND_DRINK", month=5)

    response = client.get("/spending?month=2026-05")

    assert response.status_code == 200
    assert "FOOD_AND_DRINK" in response.text
    assert "40.00" in response.text
