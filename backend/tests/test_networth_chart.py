from datetime import date, timedelta

from models import Account, BalanceSnapshot, Item
from services.networth import sparkline_points
from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_sparkline_points_normalizes_to_box():
    pts = sparkline_points([0.0, 50.0, 100.0], width=100, height=100)
    assert pts[0] == (0.0, 100.0)  # lowest value → bottom
    assert pts[1] == (50.0, 50.0)
    assert pts[2] == (100.0, 0.0)  # highest value → top


def test_sparkline_flat_series_is_midline():
    pts = sparkline_points([10.0, 10.0], width=100, height=100)
    assert pts == [(0.0, 50.0), (100.0, 50.0)]


def test_sparkline_single_point():
    assert sparkline_points([42.0], width=100, height=100) == [(0.0, 50.0)]


def test_networth_chart_requires_login(client):
    assert client.get("/api/networth", follow_redirects=False).status_code == 303


def test_networth_chart_renders_points(client, db_session):
    login(client)
    item = Item(plaid_item_id="i1", encrypted_access_token="x", institution_name="Bank")
    db_session.add(item)
    db_session.commit()
    checking = Account(
        item_id=item.id, plaid_account_id="a1", name="Checking", account_type="depository"
    )
    db_session.add(checking)
    db_session.commit()
    today = date.today()
    for offset, bal in [(2, 1000.0), (1, 1100.0), (0, 1250.0)]:
        db_session.add(
            BalanceSnapshot(
                account_id=checking.id, date=today - timedelta(days=offset), balance=bal
            )
        )
    db_session.commit()

    response = client.get("/api/networth?days=30")

    assert response.status_code == 200
    assert "<polyline" in response.text
    # Latest net worth shown.
    assert "1,250.00" in response.text
    # Three snapshots → three coordinate pairs in the polyline.
    points_attr = response.text.split('points="')[1].split('"')[0]
    assert len(points_attr.split()) == 3
