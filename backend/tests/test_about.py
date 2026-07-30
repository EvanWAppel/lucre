from tests.conftest import TEST_PASSWORD


def test_about_public_and_has_identity(client):
    response = client.get("/about")
    assert response.status_code == 200
    assert "Evan Appel" in response.text
    assert "https://github.com/EvanWAppel" in response.text
    assert "linkedin.com/in/evan-appel" in response.text
    assert "/static/evan-appel-resume.pdf" in response.text
    assert "appelew@gmail.com" in response.text


def test_about_reachable_by_owner(client):
    client.post("/login", data={"password": TEST_PASSWORD})
    assert client.get("/about").status_code == 200
