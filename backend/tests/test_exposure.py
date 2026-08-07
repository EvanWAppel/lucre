"""H15 — public exposure: indexable demo, noindex on login + owner views."""

from tests.conftest import TEST_PASSWORD


def test_robots_allows_intro_blocks_login(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    body = response.text
    assert "Disallow: /login" in body
    assert "Allow: /about" in body


def test_login_page_is_noindex(client):
    response = client.get("/login")
    assert 'name="robots"' in response.text
    assert "noindex" in response.text


def test_intro_is_indexable(client):
    response = client.get("/")  # anonymous -> intro (demo role)
    assert "noindex" not in response.text


def test_about_is_indexable(client):
    response = client.get("/about")
    assert "noindex" not in response.text


def test_owner_views_are_noindex(client):
    client.post("/login", data={"password": TEST_PASSWORD})
    response = client.get("/dashboard")
    assert "noindex" in response.text
