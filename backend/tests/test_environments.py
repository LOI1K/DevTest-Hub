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
