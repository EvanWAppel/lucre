from datetime import date

from services.bills import predict_due_date


def test_monthly_rolls_anchor_forward_to_today():
    # Anchor in the past; rolls forward one month at a time until >= today.
    due = predict_due_date("monthly", date(2026, 1, 15), None, today=date(2026, 6, 10))
    assert due == date(2026, 6, 15)


def test_monthly_anchor_already_future_is_kept():
    due = predict_due_date("monthly", date(2026, 7, 1), None, today=date(2026, 6, 10))
    assert due == date(2026, 7, 1)


def test_weekly_rolls_forward_in_seven_day_steps():
    due = predict_due_date("weekly", date(2026, 6, 1), None, today=date(2026, 6, 10))
    assert due == date(2026, 6, 15)


def test_annual_rolls_forward_a_year():
    due = predict_due_date("annual", date(2025, 3, 20), None, today=date(2026, 1, 1))
    assert due == date(2026, 3, 20)


def test_override_pins_to_day_of_month():
    due = predict_due_date("monthly", date(2026, 1, 1), 15, today=date(2026, 6, 1))
    assert due == date(2026, 6, 15)


def test_override_in_current_month_already_passed_moves_to_next_month():
    due = predict_due_date("monthly", None, 5, today=date(2026, 6, 10))
    assert due == date(2026, 7, 5)


def test_override_31st_clamps_to_february():
    # Due "on the 31st" in February clamps to the last day of the month.
    due = predict_due_date("monthly", None, 31, today=date(2026, 2, 1))
    assert due == date(2026, 2, 28)


def test_override_31st_clamps_to_30_day_month():
    due = predict_due_date("monthly", None, 31, today=date(2026, 6, 1))
    assert due == date(2026, 6, 30)


def test_override_31st_honored_in_long_month():
    # March has 31 days, so the 31st is honored even though Feb clamped.
    due = predict_due_date("monthly", None, 31, today=date(2026, 3, 1))
    assert due == date(2026, 3, 31)


def test_no_anchor_and_no_override_returns_none():
    assert predict_due_date("monthly", None, None, today=date(2026, 6, 1)) is None
