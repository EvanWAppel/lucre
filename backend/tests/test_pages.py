from tests.conftest import TEST_PASSWORD


def login(client) -> None:
    client.post("/login", data={"password": TEST_PASSWORD})


def test_app_shell_renders(client):
    login(client)
    response = client.get("/")
    assert response.status_code == 200
    assert "<html" in response.text
    assert "Lucre" in response.text
    assert "manifest.json" in response.text


def test_pwa_manifest_served(client):
    response = client.get("/static/manifest.json")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["name"] == "Lucre"
    assert manifest["display"] == "standalone"


def test_service_worker_served(client):
    assert client.get("/static/sw.js").status_code == 200
