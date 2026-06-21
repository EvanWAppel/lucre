from datetime import date

from models import Account, BalanceSnapshot, Item
from services.networth import networth_series


def make_account(db_session, name, account_type):
    item = db_session.query(Item).first()
    if item is None:
        item = Item(plaid_item_id="i1", encrypted_access_token="x", institution_name="Bank")
        db_session.add(item)
        db_session.commit()
    acct = Account(
        item_id=item.id,
        plaid_account_id=f"acct-{name}",
        name=name,
        account_type=account_type,
    )
    db_session.add(acct)
    db_session.commit()
    return acct


def snap(db_session, account, d, balance):
    db_session.add(BalanceSnapshot(account_id=account.id, date=d, balance=balance))
    db_session.commit()


def test_networth_is_cash_minus_credit_per_day(db_session):
    checking = make_account(db_session, "checking", "depository")
    card = make_account(db_session, "card", "credit")
    snap(db_session, checking, date(2026, 6, 1), 1000.0)
    snap(db_session, card, date(2026, 6, 1), 200.0)

    series = networth_series(db_session, start=date(2026, 6, 1), end=date(2026, 6, 1))

    assert series == [(date(2026, 6, 1), 800.0)]


def test_carries_forward_latest_snapshot_for_missing_days(db_session):
    checking = make_account(db_session, "checking", "depository")
    snap(db_session, checking, date(2026, 6, 1), 1000.0)
    snap(db_session, checking, date(2026, 6, 3), 1500.0)

    series = networth_series(db_session, start=date(2026, 6, 1), end=date(2026, 6, 4))

    # Jun 2 carries Jun 1's 1000; Jun 4 carries Jun 3's 1500.
    assert series == [
        (date(2026, 6, 1), 1000.0),
        (date(2026, 6, 2), 1000.0),
        (date(2026, 6, 3), 1500.0),
        (date(2026, 6, 4), 1500.0),
    ]


def test_account_excluded_before_its_first_snapshot(db_session):
    checking = make_account(db_session, "checking", "depository")
    card = make_account(db_session, "card", "credit")
    snap(db_session, checking, date(2026, 6, 1), 1000.0)
    # Card's first snapshot only appears on Jun 2.
    snap(db_session, card, date(2026, 6, 2), 300.0)

    series = networth_series(db_session, start=date(2026, 6, 1), end=date(2026, 6, 2))

    assert series == [
        (date(2026, 6, 1), 1000.0),
        (date(2026, 6, 2), 700.0),
    ]


def test_empty_when_no_snapshots(db_session):
    assert networth_series(db_session, start=date(2026, 6, 1), end=date(2026, 6, 5)) == []
