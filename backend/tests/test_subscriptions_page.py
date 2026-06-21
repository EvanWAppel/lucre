from datetime import date

from models import RecurringSeries
from services.subscriptions import active_subscriptions, annualized_total
from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def make_series(db_session, key, cadence, amount, active=True, dismissed=False):
    s = RecurringSeries(
        merchant_key=key,
        cadence=cadence,
        median_amount=amount,
        last_seen=date(2026, 6, 1),
        next_expected=date(2026, 7, 1),
        active=active,
        dismissed=dismissed,
    )
    db_session.add(s)
    db_session.commit()
    return s


def test_active_subscriptions_excludes_dismissed_and_inactive(db_session):
    make_series(db_session, "netflix", "monthly", 15.49)
    make_series(db_session, "olddub", "monthly", 5.0, active=False)
    make_series(db_session, "dropped", "monthly", 9.0, dismissed=True)

    result = active_subscriptions(db_session)

    assert [s.merchant_key for s in result] == ["netflix"]


def test_annualized_total_across_cadences():
    weekly = RecurringSeries(
        merchant_key="w",
        cadence="weekly",
        median_amount=10.0,
        last_seen=date(2026, 6, 1),
        next_expected=date(2026, 6, 8),
    )
    monthly = RecurringSeries(
        merchant_key="m",
        cadence="monthly",
        median_amount=15.0,
        last_seen=date(2026, 6, 1),
        next_expected=date(2026, 7, 1),
    )
    annual = RecurringSeries(
        merchant_key="a",
        cadence="annual",
        median_amount=120.0,
        last_seen=date(2026, 6, 1),
        next_expected=date(2027, 6, 1),
    )

    # 10*52 + 15*12 + 120*1 = 520 + 180 + 120 = 820
    assert annualized_total([weekly, monthly, annual]) == 820.0


def test_subscriptions_page_requires_login(client):
    assert client.get("/subscriptions", follow_redirects=False).status_code == 303


def test_subscriptions_page_renders(client, db_session):
    login(client)
    make_series(db_session, "netflix", "monthly", 15.49)

    response = client.get("/subscriptions")

    assert response.status_code == 200
    assert "netflix" in response.text
    assert "15.49" in response.text
    assert "monthly" in response.text


def test_dismiss_excludes_subscription(client, db_session):
    login(client)
    series = make_series(db_session, "netflix", "monthly", 15.49)

    response = client.post(f"/api/subscriptions/{series.id}/dismiss")

    assert response.status_code == 200
    db_session.refresh(series)
    assert series.dismissed is True
    assert active_subscriptions(db_session) == []
