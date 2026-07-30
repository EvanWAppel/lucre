import json
from datetime import date

import pytest

from models import Account, AlertEvent, BalanceSnapshot, RecurringSeries, Transaction
from services.demo_seed import seed_demo_data
from services.subscriptions import active_subscriptions

TODAY = date(2026, 6, 28)


@pytest.fixture
def seeded(db_session):
    seed_demo_data(db_session, TODAY)
    return db_session


def test_accounts_cover_cash_and_credit(seeded):
    accounts = seeded.query(Account).all()
    assert len(accounts) == 4
    types = {a.account_type for a in accounts}
    assert types == {"depository", "credit"}


def test_low_balance_alert_fires(seeded):
    alerts = seeded.query(AlertEvent).filter_by(type="low_balance", urgency="urgent").all()
    assert len(alerts) >= 1


def test_large_transaction_alert_fires(seeded):
    alerts = seeded.query(AlertEvent).filter_by(type="large_transaction", urgency="urgent").all()
    assert any("APPLE" in json.loads(a.payload)["name"].upper() for a in alerts)


def test_exactly_one_new_subscription_highlighted(seeded):
    alerts = seeded.query(AlertEvent).filter_by(type="new_subscription").all()
    assert len(alerts) == 1
    assert json.loads(alerts[0].payload)["merchant_key"] == "chatgpt plus"


def test_price_increase_alert_fires(seeded):
    alerts = seeded.query(AlertEvent).filter_by(type="price_increase").all()
    assert len(alerts) == 1
    payload = json.loads(alerts[0].payload)
    assert payload["merchant_key"] == "netflix"
    assert payload["new_amount"] > payload["old_amount"]


def test_recurring_has_monthly_and_annual(seeded):
    cadences = {s.cadence for s in seeded.query(RecurringSeries).all()}
    assert "monthly" in cadences
    assert "annual" in cadences


def test_subscriptions_listed(seeded):
    keys = {s.merchant_key for s in active_subscriptions(seeded)}
    assert {"netflix", "amazon prime", "chatgpt plus"} <= keys


def test_spending_has_category_variety(seeded):
    categories = {t.effective_category for t in seeded.query(Transaction).all()}
    assert len(categories) >= 5


def test_net_worth_trends_up(seeded):
    dates = sorted({s.date for s in seeded.query(BalanceSnapshot).all()})
    assert len(dates) > 10

    def total_on(d: date) -> float:
        snaps = seeded.query(BalanceSnapshot).filter_by(date=d).all()
        accounts = {a.id: a for a in seeded.query(Account).all()}
        cash = sum(s.balance for s in snaps if accounts[s.account_id].account_type == "depository")
        credit = sum(s.balance for s in snaps if accounts[s.account_id].account_type == "credit")
        return cash - credit

    assert total_on(dates[-1]) > total_on(dates[0])
