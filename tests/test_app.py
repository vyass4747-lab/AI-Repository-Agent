from fastapi.testclient import TestClient

from ai_repository_agent.app import app


client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_home_page_renders():
    response = client.get("/")

    assert response.status_code == 200
    assert "AI Repository Agent" in response.text
