from datetime import date, timedelta

from models import Item, Transaction
from plaid_client import TRANSACTIONS_DAYS_REQUESTED
from services.sync import sync_transactions
from tests.test_transactions_sync import seed_item_with_accounts


def test_requests_two_years_of_history():
    # Plaid only backfills as far back as days_requested on the link token.
    # 24 months ensures annual subscriptions are seen at least twice.
    assert TRANSACTIONS_DAYS_REQUESTED == 730


def test_large_first_sync_ingests_all_pages_from_null_cursor(db_session, fake_plaid):
    seed_item_with_accounts(db_session, fake_plaid)

    # Replace the default single page with 24 months of history across many pages
    # (Plaid returns ~100/page; the cursor loop must walk every page from null).
    start = date(2024, 6, 1)
    pages = []
    txn_index = 0
    for _page_num in range(8):
        added = []
        for _ in range(100):
            added.append(
                {
                    "plaid_transaction_id": f"txn-{txn_index}",
                    "plaid_account_id": "acct-checking-1",
                    "date": start + timedelta(days=txn_index % 700),
                    "name": f"MERCHANT {txn_index}",
                    "merchant_name": f"Merchant {txn_index}",
                    "amount": 9.99,
                    "plaid_category": "GENERAL_MERCHANDISE",
                    "pending": False,
                }
            )
            txn_index += 1
        pages.append({"added": added, "modified": [], "removed": []})
    fake_plaid.transactions_pages["access-token-1"] = pages

    result = sync_transactions(db_session, fake_plaid)

    assert result["added"] == 800
    assert db_session.query(Transaction).count() == 800
    item = db_session.query(Item).one()
    assert item.sync_cursor == "cursor-8"
