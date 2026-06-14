from datetime import date

from models import Item, Transaction
from services.sync import sync_transactions
from tests.test_sync import make_item


def seed_item_with_accounts(db_session, fake_plaid):
    """Create an item and its accounts (transactions reference accounts by id)."""
    from services.sync import sync_balances

    make_item(db_session)
    sync_balances(db_session, fake_plaid)


def test_sync_inserts_added_transactions(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)

    result = sync_transactions(db_session, fake_plaid)

    assert result["errors"] == []
    assert result["added"] == 2
    txns = db_session.query(Transaction).order_by(Transaction.date).all()
    assert [t.plaid_transaction_id for t in txns] == ["txn-netflix-1", "txn-grocery-1"]
    netflix = txns[0]
    assert netflix.name == "NETFLIX.COM"
    assert netflix.merchant_name == "Netflix"
    assert netflix.amount == 15.49
    assert netflix.plaid_category == "ENTERTAINMENT"
    assert netflix.account.plaid_account_id == "acct-checking-1"


def test_sync_persists_cursor(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    item = db_session.query(Item).one()
    assert item.sync_cursor == "cursor-1"


def test_sync_is_idempotent(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    # Re-running from the saved cursor returns an empty page (index 1 doesn't exist),
    # so no duplicates and no error.
    fake_plaid.transactions_pages["access-token-1"].append(
        {"added": [], "modified": [], "removed": []}
    )
    result = sync_transactions(db_session, fake_plaid)
    assert result["added"] == 0
    assert db_session.query(Transaction).count() == 2


def test_sync_paginates_multiple_pages(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    fake_plaid.transactions_pages["access-token-1"].append(
        {
            "added": [
                {
                    "plaid_transaction_id": "txn-spotify-1",
                    "plaid_account_id": "acct-checking-1",
                    "date": date(2026, 6, 3),
                    "name": "SPOTIFY",
                    "merchant_name": "Spotify",
                    "amount": 11.99,
                    "plaid_category": "ENTERTAINMENT",
                    "pending": False,
                }
            ],
            "modified": [],
            "removed": [],
        }
    )

    result = sync_transactions(db_session, fake_plaid)

    assert result["added"] == 3
    assert db_session.query(Transaction).count() == 3
    item = db_session.query(Item).one()
    assert item.sync_cursor == "cursor-2"


def test_sync_applies_modified(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    fake_plaid.transactions_pages["access-token-1"].append(
        {
            "added": [],
            "modified": [
                {
                    "plaid_transaction_id": "txn-netflix-1",
                    "plaid_account_id": "acct-checking-1",
                    "date": date(2026, 6, 1),
                    "name": "NETFLIX.COM",
                    "merchant_name": "Netflix",
                    "amount": 17.99,
                    "plaid_category": "ENTERTAINMENT",
                    "pending": False,
                }
            ],
            "removed": [],
        }
    )

    result = sync_transactions(db_session, fake_plaid)

    assert result["modified"] == 1
    netflix = db_session.query(Transaction).filter_by(plaid_transaction_id="txn-netflix-1").one()
    assert netflix.amount == 17.99


def test_modified_preserves_user_category(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    netflix = db_session.query(Transaction).filter_by(plaid_transaction_id="txn-netflix-1").one()
    netflix.user_category = "Streaming"
    db_session.commit()

    fake_plaid.transactions_pages["access-token-1"].append(
        {
            "added": [],
            "modified": [
                {
                    "plaid_transaction_id": "txn-netflix-1",
                    "plaid_account_id": "acct-checking-1",
                    "date": date(2026, 6, 1),
                    "name": "NETFLIX.COM",
                    "merchant_name": "Netflix",
                    "amount": 17.99,
                    "plaid_category": "GENERAL_SERVICES",
                    "pending": False,
                }
            ],
            "removed": [],
        }
    )
    sync_transactions(db_session, fake_plaid)

    db_session.refresh(netflix)
    assert netflix.plaid_category == "GENERAL_SERVICES"
    assert netflix.user_category == "Streaming"  # manual override survives


def test_sync_applies_removed(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)
    sync_transactions(db_session, fake_plaid)
    fake_plaid.transactions_pages["access-token-1"].append(
        {"added": [], "modified": [], "removed": ["txn-grocery-1"]}
    )

    result = sync_transactions(db_session, fake_plaid)

    assert result["removed"] == 1
    remaining = db_session.query(Transaction).all()
    assert [t.plaid_transaction_id for t in remaining] == ["txn-netflix-1"]


def test_one_failing_item_does_not_abort_others(db_session, fake_plaid):
    make_item(
        db_session,
        plaid_item_id="bad-item",
        access_token="missing-token",
        institution_name="Broken Bank",
    )
    seed_item_with_accounts(db_session, fake_plaid)

    result = sync_transactions(db_session, fake_plaid)

    assert result["errors"] == ["Broken Bank"]
    assert result["added"] == 2
