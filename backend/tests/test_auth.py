from app.security import hash_password, verify_password


def test_password_hashing():
    password = "Example-Password-2026!"
    hashed = hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")
    assert verify_password(password, hashed)
    assert not verify_password("wrong-password", hashed)


def test_register_user(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "Example-Password-2026!",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["username"] == "alice"
    assert data["email"] == "alice@example.com"
    assert data["role"] == "developer"
    assert data["is_active"] is True
    assert "password" not in data
    assert "password_hash" not in data


def test_duplicate_username(client):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Example-Password-2026!",
    }

    assert client.post(
        "/api/v1/auth/register",
        json=payload,
    ).status_code == 201

    payload["email"] = "another@example.com"

    response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert response.status_code == 409


def test_duplicate_email(client):
    payload = {
        "username": "alice",
        "email": "alice@example.com",
        "password": "Example-Password-2026!",
    }

    assert client.post(
        "/api/v1/auth/register",
        json=payload,
    ).status_code == 201

    payload["username"] = "another"

    response = client.post(
        "/api/v1/auth/register",
        json=payload,
    )

    assert response.status_code == 409


def test_invalid_email(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "invalid-email",
            "password": "Example-Password-2026!",
        },
    )

    assert response.status_code == 422


def test_short_password(client):
    response = client.post(
        "/api/v1/auth/register",
        json={
            "username": "alice",
            "email": "alice@example.com",
            "password": "123",
        },
    )

    assert response.status_code == 422


def test_me_without_token(client):
    response = client.get("/api/v1/users/me")

    assert response.status_code == 401


def test_me_invalid_token(client):
    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401


def test_me_with_valid_token(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "bob",
            "email": "bob@example.com",
            "password": "Example-Password-2026!",
        },
    )

    assert registration.status_code == 201

    login = client.post(
        "/api/v1/auth/login",
        data={
            "username": "bob",
            "password": "Example-Password-2026!",
        },
    )

    assert login.status_code == 200

    token = login.json()["access_token"]

    response = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["username"] == "bob"
    assert response.json()["role"] == "developer"
    assert "password_hash" not in response.json()
