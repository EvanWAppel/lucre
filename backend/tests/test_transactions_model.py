from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models import Item, Transaction
from tests.test_sync import make_item


def make_transaction(db_session, account, **overrides) -> Transaction:
    values = {
        "account_id": account.id,
        "plaid_transaction_id": "txn-1",
        "date": date(2026, 6, 1),
        "name": "NETFLIX.COM",
        "merchant_name": "Netflix",
        "amount": 15.49,
        "plaid_category": "ENTERTAINMENT",
        "pending": False,
    }
    values.update(overrides)
    txn = Transaction(**values)
    db_session.add(txn)
    db_session.commit()
    return txn


@pytest.fixture
def account(db_session, fake_plaid):
    from services.sync import sync_balances

    make_item(db_session)
    sync_balances(db_session, fake_plaid)
    from models import Account

    return db_session.query(Account).filter_by(plaid_account_id="acct-checking-1").one()


def test_transaction_roundtrip(db_session, account):
    make_transaction(db_session, account)
    txn = db_session.query(Transaction).one()
    assert txn.name == "NETFLIX.COM"
    assert txn.amount == 15.49
    assert txn.account.plaid_account_id == "acct-checking-1"
    assert txn.user_category is None


def test_plaid_transaction_id_unique(db_session, account):
    make_transaction(db_session, account)
    with pytest.raises(IntegrityError):
        make_transaction(db_session, account, name="duplicate")


def test_item_sync_cursor_defaults_null(db_session, account):
    item = db_session.query(Item).one()
    assert item.sync_cursor is None
