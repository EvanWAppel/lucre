"""Detect recurring charges (subscriptions, bills) from raw transactions.

Pure functions over (merchant_key, date, amount) tuples — no DB, no Plaid. A series
is recognised when a merchant recurs on a regular cadence with a stable-ish amount.
"""

import logging
import statistics
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# cadence name -> (expected period in days, ± day tolerance)
_CADENCES: dict[str, tuple[int, int]] = {
    "weekly": (7, 2),
    "monthly": (30, 3),
    "annual": (365, 10),
}
_AMOUNT_TOLERANCE = 0.15  # individual charges must stay within 15% of the median
_PRICE_INCREASE_THRESHOLD = 0.05  # newest charge >5% over trailing median = increase


@dataclass
class DetectedSeries:
    merchant_key: str
    cadence: str
    median_amount: float
    last_seen: date
    next_expected: date
    amounts: list[float] = field(default_factory=list)  # chronological


@dataclass
class PriceIncrease:
    old_amount: float
    new_amount: float


def _classify(interval_days: float) -> str | None:
    for name, (period, tol) in _CADENCES.items():
        if abs(interval_days - period) <= tol:
            return name
    return None


def detect_recurring(
    transactions: Iterable[tuple[str, date, float]], today: date
) -> list[DetectedSeries]:
    """Group transactions by merchant and return the regular-cadence series.

    `today` is the reference date for downstream callers (predicting overdue
    charges); detection itself is anchored on each series' own history.
    """
    by_merchant: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for merchant_key, txn_date, amount in transactions:
        if merchant_key:
            by_merchant[merchant_key].append((txn_date, amount))

    series: list[DetectedSeries] = []
    for merchant_key, entries in by_merchant.items():
        entries.sort(key=lambda e: e[0])
        dates = [e[0] for e in entries]
        amounts = [e[1] for e in entries]
        if len(dates) < 2:
            continue

        intervals = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
        cadence = _classify(statistics.median(intervals))
        if cadence is None:
            continue
        period, tol = _CADENCES[cadence]
        if not all(abs(iv - period) <= tol for iv in intervals):
            continue

        median_amount = round(statistics.median(amounts), 2)
        if median_amount <= 0:
            continue
        if any(abs(a - median_amount) > _AMOUNT_TOLERANCE * median_amount for a in amounts):
            continue

        last_seen = dates[-1]
        series.append(
            DetectedSeries(
                merchant_key=merchant_key,
                cadence=cadence,
                median_amount=median_amount,
                last_seen=last_seen,
                next_expected=last_seen + timedelta(days=period),
                amounts=amounts,
            )
        )

    series.sort(key=lambda s: s.merchant_key)
    logger.info("Detected %d recurring series", len(series))
    return series


def detect_price_increase(series: DetectedSeries) -> PriceIncrease | None:
    """Flag when the most recent charge exceeds the trailing median by >5%."""
    amounts = series.amounts
    if len(amounts) < 2:
        return None
    baseline = round(statistics.median(amounts[:-1]), 2)
    newest = amounts[-1]
    if baseline > 0 and newest > baseline * (1 + _PRICE_INCREASE_THRESHOLD):
        return PriceIncrease(old_amount=baseline, new_amount=newest)
    return None
