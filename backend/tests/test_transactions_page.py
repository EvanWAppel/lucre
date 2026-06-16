from datetime import date

from models import Account, Transaction
from services.transactions import query_transactions
from tests.conftest import TEST_PASSWORD
from tests.test_sync import make_item


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def seed(db_session, fake_plaid):
    from services.sync import sync_balances

    make_item(db_session)
    sync_balances(db_session, fake_plaid)
    checking = db_session.query(Account).filter_by(plaid_account_id="acct-checking-1").one()
    credit = db_session.query(Account).filter_by(plaid_account_id="acct-credit-1").one()
    return checking, credit


def add_txn(
    db_session,
    account,
    tid,
    day,
    name,
    amount,
    plaid_cat=None,
    user_cat=None,
    pending=False,
    month=5,
):
    txn = Transaction(
        account_id=account.id,
        plaid_transaction_id=tid,
        date=date(2026, month, day),
        name=name,
        merchant_name=name,
        amount=amount,
        plaid_category=plaid_cat,
        user_category=user_cat,
        pending=pending,
    )
    db_session.add(txn)
    db_session.commit()
    return txn


def test_query_filters_by_month(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "t-may", 15, "MAY TXN", 10.0, month=5)
    add_txn(db_session, checking, "t-jun", 15, "JUN TXN", 10.0, month=6)

    result = query_transactions(db_session, month="2026-05")

    assert [t.plaid_transaction_id for t in result.transactions] == ["t-may"]


def test_query_filters_by_account(db_session, fake_plaid):
    checking, credit = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "t-chk", 15, "CHK", 10.0)
    add_txn(db_session, credit, "t-crd", 15, "CRD", 10.0)

    result = query_transactions(db_session, account_id=credit.id)

    assert [t.plaid_transaction_id for t in result.transactions] == ["t-crd"]


def test_query_filters_by_effective_category(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "t-plaid", 15, "A", 10.0, plaid_cat="FOOD_AND_DRINK")
    add_txn(
        db_session,
        checking,
        "t-override",
        16,
        "B",
        10.0,
        plaid_cat="FOOD_AND_DRINK",
        user_cat="Groceries",
    )

    food = query_transactions(db_session, category="FOOD_AND_DRINK")
    groceries = query_transactions(db_session, category="Groceries")

    assert [t.plaid_transaction_id for t in food.transactions] == ["t-plaid"]
    assert [t.plaid_transaction_id for t in groceries.transactions] == ["t-override"]


def test_query_orders_most_recent_first(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "t-old", 1, "OLD", 10.0)
    add_txn(db_session, checking, "t-new", 20, "NEW", 10.0)

    result = query_transactions(db_session)

    assert [t.plaid_transaction_id for t in result.transactions] == ["t-new", "t-old"]


def test_query_paginates_50_per_page(db_session, fake_plaid):
    checking, _ = seed(db_session, fake_plaid)
    for i in range(60):
        add_txn(db_session, checking, f"t-{i:02d}", 1 + i % 28, f"TXN {i}", 10.0)

    page1 = query_transactions(db_session, page=1)
    page2 = query_transactions(db_session, page=2)

    assert len(page1.transactions) == 50
    assert page1.has_next is True
    assert len(page2.transactions) == 10
    assert page2.has_next is False


def test_transactions_page_requires_login(client):
    assert client.get("/transactions", follow_redirects=False).status_code == 303


def test_transactions_page_renders_with_pending_marker(client, db_session, fake_plaid):
    login(client)
    checking, _ = seed(db_session, fake_plaid)
    add_txn(db_session, checking, "t-posted", 15, "POSTED TXN", 10.0)
    add_txn(db_session, checking, "t-pending", 16, "PENDING TXN", 10.0, pending=True)

    response = client.get("/transactions")

    assert response.status_code == 200
    assert "POSTED TXN" in response.text
    assert "PENDING TXN" in response.text
    assert "pending" in response.text.lower()
