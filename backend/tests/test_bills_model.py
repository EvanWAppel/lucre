from datetime import date

from models import Bill, RecurringSeries


def make_series(db_session, key="netflix", cadence="monthly", amount=15.49):
    series = RecurringSeries(
        merchant_key=key,
        cadence=cadence,
        median_amount=amount,
        last_seen=date(2026, 6, 1),
        next_expected=date(2026, 7, 1),
    )
    db_session.add(series)
    db_session.commit()
    return series


def test_manual_bill_round_trip(db_session):
    bill = Bill(
        name="Rent",
        amount=2200.0,
        cadence="monthly",
        next_due=date(2026, 7, 1),
        due_day_override=1,
        autopay=True,
    )
    db_session.add(bill)
    db_session.commit()

    loaded = db_session.query(Bill).one()
    assert loaded.is_derived is False
    assert loaded.source == "manual"
    assert loaded.effective_name == "Rent"
    assert loaded.effective_amount == 2200.0
    assert loaded.effective_cadence == "monthly"
    assert loaded.base_due == date(2026, 7, 1)
    assert loaded.autopay is True


def test_derived_bill_sources_fields_from_series(db_session):
    series = make_series(db_session, key="netflix", amount=15.49)
    bill = Bill(recurring_series_id=series.id)
    db_session.add(bill)
    db_session.commit()

    loaded = db_session.query(Bill).one()
    assert loaded.is_derived is True
    assert loaded.source == "derived"
    assert loaded.effective_name == "netflix"
    assert loaded.effective_amount == 15.49
    assert loaded.effective_cadence == "monthly"
    assert loaded.base_due == date(2026, 7, 1)
    # autopay defaults off; no manual descriptor fields stored.
    assert loaded.autopay is False
    assert loaded.name is None
