from datetime import date, timedelta

from services.recurring import detect_price_increase, detect_recurring


def monthly_series(key, start, months, amount, day_jitter=0):
    """Build (key, date, amount) tuples roughly one month apart."""
    out = []
    d = start
    for i in range(months):
        out.append((key, d, amount))
        # advance ~1 month; vary slightly to mimic real posting dates
        d = (d.replace(day=1) + timedelta(days=32)).replace(day=start.day)
        if day_jitter and i % 2 == 0:
            d = d + timedelta(days=day_jitter)
    return out


def test_detects_monthly_subscription():
    txns = monthly_series("netflix", date(2025, 1, 5), 12, 15.49)

    series = detect_recurring(txns, today=date(2026, 1, 10))

    assert len(series) == 1
    s = series[0]
    assert s.merchant_key == "netflix"
    assert s.cadence == "monthly"
    assert s.median_amount == 15.49
    assert s.last_seen == date(2025, 12, 5)
    assert s.next_expected == date(2025, 12, 5) + timedelta(days=30)


def test_detects_annual_subscription():
    txns = [
        ("amazon prime", date(2024, 3, 15), 139.00),
        ("amazon prime", date(2025, 3, 16), 139.00),
        ("amazon prime", date(2026, 3, 15), 139.00),
    ]

    series = detect_recurring(txns, today=date(2026, 4, 1))

    assert len(series) == 1
    assert series[0].cadence == "annual"


def test_detects_variable_utility_bill_within_amount_tolerance():
    # Amounts wander but stay within 15% of the median; timing is regular monthly.
    amounts = [100.0, 112.0, 95.0, 108.0, 103.0, 99.0]
    txns = [
        ("city power", date(2025, 1, 10) + timedelta(days=30 * i), amt)
        for i, amt in enumerate(amounts)
    ]

    series = detect_recurring(txns, today=date(2025, 8, 1))

    assert len(series) == 1
    assert series[0].cadence == "monthly"


def test_irregular_gas_station_is_not_recurring():
    # Random-ish intervals and swinging amounts: not a subscription.
    days = [0, 3, 21, 26, 40, 47, 70]
    amounts = [42.0, 18.5, 60.0, 25.0, 51.0, 33.0, 47.0]
    txns = [
        ("shell oil", date(2025, 1, 1) + timedelta(days=d), a)
        for d, a in zip(days, amounts, strict=True)
    ]

    series = detect_recurring(txns, today=date(2025, 4, 1))

    assert series == []


def test_single_occurrence_is_not_recurring():
    txns = [("one off", date(2025, 5, 1), 9.99)]
    assert detect_recurring(txns, today=date(2025, 6, 1)) == []


def test_amount_swing_beyond_tolerance_rejected():
    # Regular monthly timing, but amounts swing far beyond 15%.
    amounts = [10.0, 50.0, 12.0, 80.0]
    txns = [("noisy", date(2025, 1, 1) + timedelta(days=30 * i), a) for i, a in enumerate(amounts)]
    assert detect_recurring(txns, today=date(2025, 6, 1)) == []


def test_price_increase_flagged_above_5_percent():
    series = detect_recurring(
        [
            ("netflix", date(2025, 1, 1) + timedelta(days=30 * i), amt)
            for i, amt in enumerate([15.49, 15.49, 15.49, 16.99])
        ],
        today=date(2025, 6, 1),
    )[0]

    increase = detect_price_increase(series)

    assert increase is not None
    assert increase.old_amount == 15.49
    assert increase.new_amount == 16.99


def test_no_price_increase_when_stable():
    series = detect_recurring(
        [("spotify", date(2025, 1, 1) + timedelta(days=30 * i), 11.99) for i in range(5)],
        today=date(2025, 7, 1),
    )[0]

    assert detect_price_increase(series) is None
