from crypto import encrypt
from models import Account, Item
from services.sync import sync_balances


def make_item(
    db_session,
    plaid_item_id="plaid-item-1",
    access_token="access-token-1",
    institution_name="Fake Bank",
) -> Item:
    item = Item(
        plaid_item_id=plaid_item_id,
        encrypted_access_token=encrypt(access_token),
        institution_name=institution_name,
    )
    db_session.add(item)
    db_session.commit()
    return item


def test_sync_creates_new_accounts(db_session, fake_plaid):
    make_item(db_session)
    result = sync_balances(db_session, fake_plaid)
    assert result["items_synced"] == 1
    assert result["errors"] == []
    accounts = db_session.query(Account).order_by(Account.plaid_account_id).all()
    assert [a.plaid_account_id for a in accounts] == ["acct-checking-1", "acct-credit-1"]
    assert accounts[0].balance == 1500.25


def test_sync_updates_existing_balance(db_session, fake_plaid):
    make_item(db_session)
    sync_balances(db_session, fake_plaid)
    fake_plaid.accounts["access-token-1"][0]["balance"] = 1600.00

    result = sync_balances(db_session, fake_plaid)

    assert result["errors"] == []
    account = db_session.query(Account).filter_by(plaid_account_id="acct-checking-1").one()
    assert account.balance == 1600.00
    # Still two accounts — the sync upserts, never duplicates.
    assert db_session.query(Account).count() == 2


def test_one_failing_item_does_not_abort_others(db_session, fake_plaid):
    make_item(
        db_session,
        plaid_item_id="bad-item",
        access_token="missing-token",
        institution_name="Broken Bank",
    )
    make_item(db_session)

    result = sync_balances(db_session, fake_plaid)

    assert result["items_synced"] == 1
    assert result["errors"] == ["Broken Bank"]
    assert db_session.query(Account).count() == 2
