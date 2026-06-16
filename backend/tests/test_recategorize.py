from models import Transaction
from tests.conftest import TEST_PASSWORD
from tests.test_transactions_page import add_txn, seed


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_recategorize_requires_login(client, db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    txn = add_txn(db_session, checking, "t-1", 15, "A", 10.0, plaid_cat="FOOD_AND_DRINK")
    response = client.patch(
        f"/api/transactions/{txn.id}/category",
        data={"category": "Groceries"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_recategorize_sets_user_category(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    txn = add_txn(db_session, checking, "t-1", 15, "A", 10.0, plaid_cat="FOOD_AND_DRINK")

    response = client.patch(f"/api/transactions/{txn.id}/category", data={"category": "Groceries"})

    assert response.status_code == 200
    db_session.refresh(txn)
    assert txn.user_category == "Groceries"
    assert txn.effective_category == "Groceries"
    assert "Groceries" in response.text


def test_recategorize_blank_clears_override(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    txn = add_txn(
        db_session, checking, "t-1", 15, "A", 10.0, plaid_cat="FOOD_AND_DRINK", user_cat="Groceries"
    )

    client.patch(f"/api/transactions/{txn.id}/category", data={"category": ""})

    db_session.refresh(txn)
    assert txn.user_category is None
    assert txn.effective_category == "FOOD_AND_DRINK"


def test_recategorize_unknown_transaction_404(client, db_session, fake_plaid):
    login(client)
    seed(db_session, fake_plaid)
    response = client.patch("/api/transactions/9999/category", data={"category": "X"})
    assert response.status_code == 404
    assert db_session.query(Transaction).count() == 0
