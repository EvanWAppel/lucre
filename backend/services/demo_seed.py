"""Generate the recruiter-facing demo dataset (PRD H3).

Deterministic but anchored to ``today``: a plausible ~6-month financial history
that *also* deliberately trips every smart feature — a brand-new subscription, a
price increase on an existing one, a low balance, and a large transaction — so the
detection + alert pipeline visibly fires.

Derived data (recurring series, bills, alerts, balance snapshots) is produced by
the *real* services rather than hand-written, so the demo exercises the same code
paths as production. Raw transactions are inserted directly (no Plaid) for full
control over the narrative.
"""

import logging
from datetime import date, timedelta
from itertools import count
from random import Random

from sqlalchemy.orm import Session

from models import (
    Account,
    AlertEvent,
    AlertSettings,
    BalanceSnapshot,
    Item,
    Transaction,
)
from services.alert_rules import run_post_sync_alerts
from services.bills import seed_derived_bills
from services.merchants import merchant_key as compute_merchant_key
from services.subscriptions import sync_recurring

logger = logging.getLogger(__name__)

# Trips the large-transaction urgent alert.
LARGE_TRANSACTION_AMOUNT = 1000.0
# The checking account ends below this, tripping the low-balance urgent alert.
CHECKING_LOW_THRESHOLD = 500.0

_RNG_SEED = 20260601

# Starting balances ~6 months ago, used to draw an upward net-worth curve toward
# each account's current balance.
_SNAPSHOT_STARTS = {
    "demo-checking": 2200.0,
    "demo-savings": 9000.0,
    "demo-rewards": 760.0,
    "demo-travel": 980.0,
}

# Discretionary merchants by Plaid category — gives the spending-by-category view
# substance. Irregular dates/amounts keep these from being detected as recurring.
_DISCRETIONARY = {
    "FOOD_AND_DRINK": [
        ("WHOLE FOODS MKT", "Whole Foods"),
        ("TRADER JOES #455", "Trader Joe's"),
        ("CHIPOTLE 1123", "Chipotle"),
        ("BLUE BOTTLE COFFEE", "Blue Bottle Coffee"),
    ],
    "TRAVEL": [
        ("UNITED AIRLINES", "United Airlines"),
        ("MARRIOTT HOTELS", "Marriott"),
        ("UBER TRIP", "Uber"),
    ],
    "GENERAL_MERCHANDISE": [
        ("TARGET 00021", "Target"),
        ("AMAZON MKTP US", "Amazon"),
        ("BEST BUY #114", "Best Buy"),
    ],
    "TRANSPORTATION": [
        ("SHELL OIL 5567", "Shell"),
        ("CHEVRON 220", "Chevron"),
    ],
    "PERSONAL_CARE": [
        ("CVS PHARMACY", "CVS"),
        ("GREAT CLIPS", "Great Clips"),
    ],
}


def _monthly_dates(anchor: date, n: int) -> list[date]:
    """n charge dates ending at ``anchor``, 30 days apart (chronological order)."""
    return [anchor - timedelta(days=30 * i) for i in range(n - 1, -1, -1)]


def seed_demo_data(session: Session, today: date | None = None) -> None:
    """Populate ``session``'s database with the full demo dataset."""
    today = today or date.today()
    rng = Random(_RNG_SEED)
    ids = count(1)

    def add_txn(
        account: Account, *, name: str, merchant: str, amount: float, d: date, category: str
    ) -> None:
        session.add(
            Transaction(
                account_id=account.id,
                plaid_transaction_id=f"demo-txn-{next(ids)}",
                date=d,
                name=name,
                merchant_name=merchant,
                amount=amount,
                plaid_category=category,
                merchant_key=compute_merchant_key(merchant or name),
                pending=False,
            )
        )

    session.add(AlertSettings(id=1, large_transaction_amount=LARGE_TRANSACTION_AMOUNT))

    bank = Item(
        plaid_item_id="demo-bank", encrypted_access_token="demo", institution_name="Everyday Bank"
    )
    issuer = Item(
        plaid_item_id="demo-cards", encrypted_access_token="demo", institution_name="Summit Card"
    )
    session.add_all([bank, issuer])
    session.flush()

    checking = Account(
        item_id=bank.id,
        plaid_account_id="demo-checking",
        name="Everyday Checking",
        account_type="depository",
        subtype="checking",
        balance=180.42,
        low_balance_threshold=CHECKING_LOW_THRESHOLD,
    )
    savings = Account(
        item_id=bank.id,
        plaid_account_id="demo-savings",
        name="Rainy Day Savings",
        account_type="depository",
        subtype="savings",
        balance=14200.00,
    )
    rewards = Account(
        item_id=issuer.id,
        plaid_account_id="demo-rewards",
        name="Summit Rewards Card",
        account_type="credit",
        subtype="credit card",
        balance=842.55,
    )
    travel = Account(
        item_id=issuer.id,
        plaid_account_id="demo-travel",
        name="Travel Miles Card",
        account_type="credit",
        subtype="credit card",
        balance=1203.10,
    )
    session.add_all([checking, savings, rewards, travel])
    session.flush()

    # --- Recurring subscriptions -------------------------------------------------
    # Netflix: monthly, with a recent price increase (15.49 -> 16.99, ~10%: above
    # the 5% alert threshold yet within the 15% band that keeps it one series).
    netflix_dates = _monthly_dates(today - timedelta(days=5), 6)
    for d in netflix_dates:
        amount = 16.99 if d == netflix_dates[-1] else 15.49
        add_txn(
            rewards,
            name="NETFLIX.COM",
            merchant="Netflix",
            amount=amount,
            d=d,
            category="ENTERTAINMENT",
        )

    # Spotify: monthly, last charge ~28 days ago so its next due lands within the
    # bill-due-soon window (exercises the derived-bills + digest path).
    for d in _monthly_dates(today - timedelta(days=28), 5):
        add_txn(
            rewards,
            name="SPOTIFY P1234",
            merchant="Spotify",
            amount=11.99,
            d=d,
            category="ENTERTAINMENT",
        )

    # Planet Fitness: monthly.
    for d in _monthly_dates(today - timedelta(days=12), 6):
        add_txn(
            rewards,
            name="PLANET FITNESS",
            merchant="Planet Fitness",
            amount=24.99,
            d=d,
            category="PERSONAL_CARE",
        )

    # City Power: monthly utility — amount varies but stays within the 15% band.
    power_amounts = [98.40, 102.10, 95.75, 110.30, 99.90, 104.20]
    for amount, d in zip(power_amounts, _monthly_dates(today - timedelta(days=8), 6), strict=True):
        add_txn(
            checking,
            name="CITY POWER UTIL",
            merchant="City Power",
            amount=amount,
            d=d,
            category="RENT_AND_UTILITIES",
        )

    # Amazon Prime: annual (two charges ~365 days apart -> annual cadence on show).
    for d in (today - timedelta(days=380), today - timedelta(days=15)):
        add_txn(
            travel,
            name="AMZN Prime",
            merchant="Amazon Prime",
            amount=139.00,
            d=d,
            category="GENERAL_MERCHANDISE",
        )

    # --- Income (negative = money in; excluded from recurring detection) ----------
    payday = today - timedelta(days=2)
    for i in range(12):
        add_txn(
            checking,
            name="ACME CORP PAYROLL",
            merchant="Acme Corp",
            amount=-2600.00,
            d=payday - timedelta(days=14 * i),
            category="INCOME",
        )

    # --- Discretionary spend across categories (~6 months) -----------------------
    categories = list(_DISCRETIONARY.items())
    accounts = [rewards, travel, checking]
    for day_offset in range(182):
        d = today - timedelta(days=day_offset)
        for _ in range(rng.randint(0, 2)):
            category, merchants = rng.choice(categories)
            name, merchant = rng.choice(merchants)
            add_txn(
                rng.choice(accounts),
                name=name,
                merchant=merchant,
                amount=round(rng.uniform(8, 120), 2),
                d=d,
                category=category,
            )

    # --- A large one-off purchase (trips the large-transaction alert) -------------
    add_txn(
        rewards,
        name="APPLE STORE R123",
        merchant="Apple",
        amount=1299.00,
        d=today - timedelta(days=2),
        category="GENERAL_MERCHANDISE",
    )

    session.commit()

    # Phase 1: detect the baseline series, then drop the resulting "new subscription"
    # noise so exactly one deliberate new sub stands out after phase 2.
    sync_recurring(session, today)
    session.query(AlertEvent).filter_by(type="new_subscription").delete()
    session.commit()

    # Phase 2: a brand-new subscription that started ~1 month ago -> one new-sub alert.
    for d in _monthly_dates(today - timedelta(days=3), 2):
        add_txn(
            rewards,
            name="OPENAI CHATGPT",
            merchant="ChatGPT Plus",
            amount=20.00,
            d=d,
            category="GENERAL_MERCHANDISE",
        )
    session.commit()
    sync_recurring(session, today)

    _seed_snapshots(session, today, [checking, savings, rewards, travel], rng)

    seed_derived_bills(session, today)
    run_post_sync_alerts(session, None, today)
    logger.info("Demo data seeded (today=%s)", today)


def _seed_snapshots(session: Session, today: date, accounts: list[Account], rng: Random) -> None:
    """Weekly balance snapshots over ~6 months, trending to each current balance."""
    weeks = 26
    for account in accounts:
        start = _SNAPSHOT_STARTS[account.plaid_account_id]
        end = account.balance or 0.0
        for i in range(weeks, -1, -1):
            d = today - timedelta(days=7 * i)
            fraction = (weeks - i) / weeks
            value = start + (end - start) * fraction
            jitter = 0.0 if i == 0 else rng.uniform(-40, 40)  # today's point is exact
            session.add(
                BalanceSnapshot(account_id=account.id, date=d, balance=round(value + jitter, 2))
            )
    session.commit()


def demo_seed(session: Session) -> None:
    """Seed callback for DemoStoreManager (anchors to the current date)."""
    seed_demo_data(session)
