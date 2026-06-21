from datetime import date

from models import Bill, RecurringSeries
from services.bills import seed_derived_bills


def make_series(db_session, key, *, active=True, dismissed=False):
    series = RecurringSeries(
        merchant_key=key,
        cadence="monthly",
        median_amount=15.0,
        last_seen=date(2026, 6, 1),
        next_expected=date(2026, 7, 1),
        active=active,
        dismissed=dismissed,
    )
    db_session.add(series)
    db_session.commit()
    return series


def test_seeds_one_bill_per_active_series(db_session):
    make_series(db_session, "netflix")
    make_series(db_session, "spotify")

    result = seed_derived_bills(db_session, today=date(2026, 6, 15))

    assert result["created"] == 2
    bills = db_session.query(Bill).all()
    assert {b.series.merchant_key for b in bills} == {"netflix", "spotify"}


def test_seed_is_idempotent(db_session):
    make_series(db_session, "netflix")
    seed_derived_bills(db_session, today=date(2026, 6, 15))

    result = seed_derived_bills(db_session, today=date(2026, 6, 16))

    assert result["created"] == 0
    assert db_session.query(Bill).count() == 1


def test_dismissal_removes_derived_bill(db_session):
    series = make_series(db_session, "netflix")
    seed_derived_bills(db_session, today=date(2026, 6, 15))
    assert db_session.query(Bill).count() == 1

    series.dismissed = True
    db_session.commit()
    result = seed_derived_bills(db_session, today=date(2026, 6, 16))

    assert result["removed"] == 1
    assert db_session.query(Bill).count() == 0


def test_inactive_series_removes_derived_bill(db_session):
    series = make_series(db_session, "netflix")
    seed_derived_bills(db_session, today=date(2026, 6, 15))

    series.active = False
    db_session.commit()
    seed_derived_bills(db_session, today=date(2026, 6, 16))

    assert db_session.query(Bill).count() == 0


def test_manual_bills_untouched_by_seed(db_session):
    db_session.add(Bill(name="Rent", amount=2000.0, cadence="monthly", next_due=date(2026, 7, 1)))
    db_session.commit()

    seed_derived_bills(db_session, today=date(2026, 6, 15))

    assert db_session.query(Bill).filter(Bill.recurring_series_id.is_(None)).count() == 1
