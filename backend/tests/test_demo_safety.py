"""H12 — demo safety sweep: demo-reachable routes never call Plaid or send email."""

from plaid_client import get_plaid_client

DEMO_ROUTES = [
    "/",
    "/dashboard",
    "/transactions",
    "/spending",
    "/subscriptions",
    "/bills",
    "/settings",
    "/alerts/preview",
    "/demo/connect",
]


class _ExplodingPlaid:
    def __getattr__(self, _name):
        raise AssertionError("a demo route must never call Plaid")


def test_demo_routes_never_call_plaid_or_send_email(client, fake_email):
    from main import app

    app.dependency_overrides[get_plaid_client] = lambda: _ExplodingPlaid()
    for route in DEMO_ROUTES:
        response = client.get(route, follow_redirects=False)
        assert response.status_code in (200, 303), f"{route} -> {response.status_code}"
    assert fake_email.sent == []  # nothing emailed across the whole demo surface
