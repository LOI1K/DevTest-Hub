from itertools import count

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import environments as environment_module


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    environment_module.environments.clear()
    environment_module.environment_ids = count(1)

    yield

    environment_module.environments.clear()


def test_health():
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_environment_list():
    response = client.get("/api/v1/environments")

    assert response.status_code == 200
    assert response.json() == []


def test_create_environment():
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "nginx",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["id"] == 1
    assert data["name"] == "auth-testing"
    assert data["template"] == "nginx"
    assert data["status"] == "pending"

    list_response = client.get("/api/v1/environments")
    assert len(list_response.json()) == 1


def test_invalid_name():
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "My Env",
            "template": "nginx",
        },
    )

    assert response.status_code == 422


def test_invalid_template():
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "unknown",
        },
    )

    assert response.status_code == 422
