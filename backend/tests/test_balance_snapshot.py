from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from models import Account, BalanceSnapshot
from services.snapshots import write_snapshots
from tests.test_sync import make_item


def seed_accounts(db_session, fake_plaid):
    from services.sync import sync_balances

    make_item(db_session)
    sync_balances(db_session, fake_plaid)
    return db_session.query(Account).order_by(Account.plaid_account_id).all()


def test_write_snapshots_one_per_account(db_session, fake_plaid):
    accounts = seed_accounts(db_session, fake_plaid)

    write_snapshots(db_session, today=date(2026, 6, 20))

    snaps = db_session.query(BalanceSnapshot).all()
    assert len(snaps) == len(accounts)
    by_account = {s.account_id: s.balance for s in snaps}
    assert by_account[accounts[0].id] == accounts[0].balance


def test_write_snapshots_idempotent_per_day(db_session, fake_plaid):
    seed_accounts(db_session, fake_plaid)

    write_snapshots(db_session, today=date(2026, 6, 20))
    write_snapshots(db_session, today=date(2026, 6, 20))

    # Re-running the same day updates in place, never duplicates.
    assert db_session.query(BalanceSnapshot).count() == 2


def test_write_snapshots_updates_balance_same_day(db_session, fake_plaid):
    accounts = seed_accounts(db_session, fake_plaid)
    write_snapshots(db_session, today=date(2026, 6, 20))

    accounts[0].balance = 9999.0
    db_session.commit()
    write_snapshots(db_session, today=date(2026, 6, 20))

    snap = (
        db_session.query(BalanceSnapshot)
        .filter_by(account_id=accounts[0].id, date=date(2026, 6, 20))
        .one()
    )
    assert snap.balance == 9999.0


def test_unique_account_date_constraint(db_session, fake_plaid):
    accounts = seed_accounts(db_session, fake_plaid)
    db_session.add(BalanceSnapshot(account_id=accounts[0].id, date=date(2026, 6, 20), balance=1.0))
    db_session.commit()
    db_session.add(BalanceSnapshot(account_id=accounts[0].id, date=date(2026, 6, 20), balance=2.0))
    with pytest.raises(IntegrityError):
        db_session.commit()
