from datetime import date

from models import Bill, RecurringSeries
from services.bills import upcoming_bills, upcoming_total
from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def make_manual(db_session, name, amount, cadence, next_due, **kw):
    bill = Bill(name=name, amount=amount, cadence=cadence, next_due=next_due, **kw)
    db_session.add(bill)
    db_session.commit()
    return bill


def make_derived(db_session, key, amount, next_expected, active=True, dismissed=False):
    series = RecurringSeries(
        merchant_key=key,
        cadence="monthly",
        median_amount=amount,
        last_seen=date(2026, 6, 1),
        next_expected=next_expected,
        active=active,
        dismissed=dismissed,
    )
    db_session.add(series)
    db_session.commit()
    bill = Bill(recurring_series_id=series.id)
    db_session.add(bill)
    db_session.commit()
    return bill


# --- upcoming_bills service ---


def test_upcoming_includes_window_and_excludes_beyond_30_days(db_session):
    today = date(2026, 6, 10)
    make_manual(db_session, "Rent", 2000.0, "monthly", date(2026, 6, 20))
    make_manual(db_session, "FarOff", 50.0, "monthly", date(2026, 8, 1))  # >30 days

    items = upcoming_bills(db_session, today)

    assert [i.name for i in items] == ["Rent"]


def test_upcoming_sorted_and_totaled(db_session):
    today = date(2026, 6, 10)
    make_manual(db_session, "Later", 100.0, "monthly", date(2026, 6, 25))
    make_manual(db_session, "Sooner", 30.0, "monthly", date(2026, 6, 12))
    make_derived(db_session, "netflix", 15.49, date(2026, 6, 15))

    items = upcoming_bills(db_session, today)

    assert [i.name for i in items] == ["Sooner", "netflix", "Later"]
    assert [i.source for i in items] == ["manual", "derived", "manual"]
    assert upcoming_total(items) == 145.49


def test_upcoming_excludes_dismissed_derived_bill(db_session):
    today = date(2026, 6, 10)
    make_derived(db_session, "netflix", 15.49, date(2026, 6, 15), dismissed=True)

    assert upcoming_bills(db_session, today) == []


# --- page + CRUD routes ---


def test_bills_page_requires_login(client):
    assert client.get("/bills", follow_redirects=False).status_code == 303


def test_bills_page_renders_with_badge(client, db_session):
    login(client)
    make_derived(db_session, "netflix", 15.49, date.today())

    response = client.get("/bills")

    assert response.status_code == 200
    assert "netflix" in response.text
    assert "derived" in response.text


def test_create_manual_bill(client, db_session):
    login(client)

    response = client.post(
        "/bills/new",
        data={
            "name": "Rent",
            "amount": "2200",
            "cadence": "monthly",
            "next_due": "2026-07-01",
            "autopay": "true",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    bill = db_session.query(Bill).one()
    assert bill.name == "Rent"
    assert bill.amount == 2200.0
    assert bill.autopay is True


def test_edit_manual_bill(client, db_session):
    login(client)
    bill = make_manual(db_session, "Rent", 2000.0, "monthly", date(2026, 7, 1))

    response = client.post(
        f"/bills/{bill.id}/edit",
        data={
            "name": "Rent",
            "amount": "2300",
            "cadence": "monthly",
            "next_due": "2026-07-01",
            "due_day_override": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(bill)
    assert bill.amount == 2300.0
    assert bill.due_day_override == 1


def test_edit_derived_bill_only_updates_override_and_autopay(client, db_session):
    login(client)
    bill = make_derived(db_session, "netflix", 15.49, date(2026, 7, 1))

    response = client.post(
        f"/bills/{bill.id}/edit",
        data={"due_day_override": "20", "autopay": "true"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    db_session.refresh(bill)
    assert bill.due_day_override == 20
    assert bill.autopay is True
    # Descriptor fields stay sourced from the series.
    assert bill.name is None
    assert bill.effective_amount == 15.49


def test_delete_manual_bill(client, db_session):
    login(client)
    bill = make_manual(db_session, "Rent", 2000.0, "monthly", date(2026, 7, 1))

    response = client.post(f"/bills/{bill.id}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert db_session.query(Bill).count() == 0


def test_delete_derived_bill_rejected(client, db_session):
    login(client)
    bill = make_derived(db_session, "netflix", 15.49, date(2026, 7, 1))

    response = client.post(f"/bills/{bill.id}/delete", follow_redirects=False)

    assert response.status_code == 400
    assert db_session.query(Bill).count() == 1
