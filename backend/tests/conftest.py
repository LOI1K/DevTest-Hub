
import pytest

from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.main import app


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
    with test_engine.connect() as connection:
        transaction = connection.begin()

        try:
            actual_database = connection.scalar(
                text("SELECT current_database()")
            )

            if actual_database != "devtesthub_test":
                raise RuntimeError("Wrong test database")

            def override_get_db():
                with Session(
                    bind=connection,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    yield session

            app.dependency_overrides[get_db] = override_get_db

            with TestClient(app) as test_client:
                yield test_client

        finally:
            app.dependency_overrides.pop(get_db, None)
            transaction.rollback()
