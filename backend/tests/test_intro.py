from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_root_shows_intro_for_anonymous(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Launch the demo" in response.text
    assert "FastAPI" in response.text  # stack badge
    assert "/about" in response.text


def test_root_redirects_owner_to_dashboard(client):
    login(client)
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"


def test_dashboard_open_to_demo_with_banner(client):
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "fake data" in response.text  # demo banner
    assert "Sign in" in response.text  # discreet owner login link


def test_owner_dashboard_has_no_demo_banner(client):
    login(client)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "fake data" not in response.text
    assert "Sign out" in response.text


def test_real_connect_is_owner_only(client):
    response = client.get("/link", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_real_sync_is_owner_only(client):
    response = client.post("/api/sync", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
