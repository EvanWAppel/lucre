from datetime import date, timedelta

from models import Account, RecurringSeries, Transaction
from services.sync import run_full_sync
from tests.test_sync import make_item


def test_full_sync_runs_balances_transactions_and_recurring(db_session, fake_plaid):
    make_item(db_session)
    # Replace the default page with a 6-month Netflix history forming a series.
    fake_plaid.transactions_pages["access-token-1"] = [
        {
            "added": [
                {
                    "plaid_transaction_id": f"netflix-{i}",
                    "plaid_account_id": "acct-checking-1",
                    "date": date(2025, 1, 5) + timedelta(days=30 * i),
                    "name": "NETFLIX.COM",
                    "merchant_name": "Netflix",
                    "amount": 15.49,
                    "plaid_category": "ENTERTAINMENT",
                    "pending": False,
                }
                for i in range(6)
            ],
            "modified": [],
            "removed": [],
        }
    ]

    result = run_full_sync(db_session, fake_plaid, today=date(2025, 7, 1))

    # Balances synced (accounts created), transactions ingested, series detected.
    assert db_session.query(Account).count() == 2
    assert db_session.query(Transaction).count() == 6
    series = db_session.query(RecurringSeries).one()
    assert series.merchant_key == "netflix"
    assert result["recurring"]["detected"] == 1
    assert result["transactions"]["added"] == 6
