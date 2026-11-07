import pytest


@pytest.fixture(autouse=True)
def authenticate_environment_tests(client):
    password = "Example-Password-2026!"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "firstdeveloper",
            "email": "firstdeveloper@example.com",
            "password": password,
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        data={
            "username": "firstdeveloper",
            "password": password,
        },
    )
    assert login.status_code == 200

    token = login.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    yield

    client.headers.pop("Authorization", None)


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
    created = client.post(
        "/api/v1/environments",
        json={
            "name": "auth-testing",
            "template": "nginx",
        },
    )

    assert created.status_code == 201

    environment_id = created.json()["id"]

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
        json={
            "name": "old-name",
            "template": "nginx",
        },
    )

    assert created.status_code == 201

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

    assert saved.status_code == 200
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
        json={
            "name": "delete-test",
            "template": "nginx",
        },
    )

    assert created.status_code == 201

    environment_id = created.json()["id"]

    response = client.delete(
        f"/api/v1/environments/{environment_id}"
    )

    assert response.status_code == 202
    assert response.json()["id"] == environment_id
    assert response.json()["status"] == "deleting"

    check = client.get(
        f"/api/v1/environments/{environment_id}"
    )

    assert check.status_code == 200
    assert check.json()["status"] == "deleting"

    repeated = client.delete(
        f"/api/v1/environments/{environment_id}"
    )

    assert repeated.status_code == 202
    assert repeated.json()["status"] == "deleting"


def test_delete_nonexistent_environment(client):
    response = client.delete(
        "/api/v1/environments/999999"
    )

    assert response.status_code == 404


def test_environment_requires_authentication(client):
    token = client.headers.pop("Authorization")

    try:
        response = client.get("/api/v1/environments")
    finally:
        client.headers["Authorization"] = token

    assert response.status_code == 401


def test_cannot_access_another_users_environment(client):
    # Первый разработчик создаёт собственную среду
    created = client.post(
        "/api/v1/environments",
        json={
            "name": "private-environment",
            "template": "nginx",
        },
    )

    assert created.status_code == 201
    environment_id = created.json()["id"]

    # Регистрируем второго разработчика
    password = "Example-Password-2026!"

    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "seconddeveloper",
            "email": "seconddeveloper@example.com",
            "password": password,
        },
    )
    assert registration.status_code == 201

    # Получаем JWT второго разработчика
    login = client.post(
        "/api/v1/auth/login",
        data={
            "username": "seconddeveloper",
            "password": password,
        },
    )

    assert login.status_code == 200

    second_token = login.json()["access_token"]
    second_headers = {
        "Authorization": f"Bearer {second_token}"
    }

    # Второй разработчик не видит чужие среды
    response = client.get(
        "/api/v1/environments",
        headers=second_headers,
    )
    assert response.status_code == 200
    assert response.json() == []

    # Не может получить чужую среду по ID
    response = client.get(
        f"/api/v1/environments/{environment_id}",
        headers=second_headers,
    )
    assert response.status_code == 404

    # Не может изменить чужую среду
    response = client.patch(
        f"/api/v1/environments/{environment_id}",
        json={"name": "changed-name"},
        headers=second_headers,
    )
    assert response.status_code == 404

    # Не может удалить чужую среду
    response = client.delete(
        f"/api/v1/environments/{environment_id}",
        headers=second_headers,
    )
    assert response.status_code == 404

    # Первый разработчик по-прежнему видит свою среду
    response = client.get(
        f"/api/v1/environments/{environment_id}"
    )
    assert response.status_code == 200
    assert response.json()["name"] == "private-environment"
