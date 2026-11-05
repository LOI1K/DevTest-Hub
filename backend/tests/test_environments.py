import pytest

from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.main import app


# Подключение только к тестовой базе
test_database_url = URL.create(
    drivername="postgresql+psycopg",
    username=settings.postgres_user,
    password=settings.postgres_password,
    host="127.0.0.1",
    port=5434,
    database="devtesthub_test",
)

test_engine = create_engine(
    test_database_url,
    pool_pre_ping=True,
)


@pytest.fixture
def client():
    # Защита от случайного подключения к основной базе
    if test_database_url.database != "devtesthub_test":
        raise RuntimeError("Tests must use devtesthub_test")

    with test_engine.connect() as connection:
        transaction = connection.begin()

        def override_get_db():
            with Session(
                bind=connection,
                join_transaction_mode="create_savepoint",
            ) as session:
                yield session

        try:
            actual_database = connection.scalar(
                text("SELECT current_database()")
            )

            if actual_database != "devtesthub_test":
                raise RuntimeError("Wrong test database")

            app.dependency_overrides[get_db] = override_get_db

            with TestClient(app) as test_client:
                yield test_client

        finally:
            app.dependency_overrides.pop(get_db, None)
            transaction.rollback()


def test_health(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_empty_environment_list(client):
    response = client.get("/api/v1/environments")

    assert response.status_code == 200
    assert response.json() == []


def test_create_environment(client):
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "nginx",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert isinstance(data["id"], int)
    assert data["id"] > 0
    assert data["name"] == "auth-testing"
    assert data["template"] == "nginx"
    assert data["status"] == "pending"

    list_response = client.get("/api/v1/environments")

    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
    assert list_response.json()[0]["id"] == data["id"]


def test_invalid_name(client):
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "My Env",
            "template": "nginx",
        },
    )

    assert response.status_code == 422


def test_invalid_template(client):
    response = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "unknown",
        },
    )

    assert response.status_code == 422


def test_get_environment_by_id(client):
    create_response = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "nginx",
        },
    )

    assert create_response.status_code == 201

    environment_id = create_response.json()["id"]

    response = client.get(
        f"/api/v1/environments/{environment_id}"
    )

    assert response.status_code == 200
    assert response.json()["id"] == environment_id
    assert response.json()["name"] == "auth-testing"


def test_get_nonexistent_environment(client):
    response = client.get("/api/v1/environments/999999")

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Environment not found"
    }

def test_update_environment(client):
    created = client.post(
        "/api/v1/environments",
        json={"name": "old-name", "template": "nginx"},
    )

    environment_id = created.json()["id"]

    response = client.patch(
        f"/api/v1/environments/{environment_id}",
        json={"name": "new-name"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "new-name"

    saved = client.get(
        f"/api/v1/environments/{environment_id}"
    )

    assert saved.json()["name"] == "new-name"


def test_update_nonexistent_environment(client):
    response = client.patch(
        "/api/v1/environments/999999",
        json={"name": "new-name"},
    )

    assert response.status_code == 404


def test_delete_environment(client):
    created = client.post(
        "/api/v1/environments",
        json={"name": "delete-test", "template": "nginx"},
    )

    environment_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/environments/{environment_id}"
    )

    assert response.status_code == 204

    check = client.get(
        f"/api/v1/environments/{environment_id}"
    )

    assert check.status_code == 404


def test_delete_nonexistent_environment(client):
    response = client.delete(
        "/api/v1/environments/999999"
    )

    assert response.status_code == 404
