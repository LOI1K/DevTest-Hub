from unittest.mock import MagicMock, Mock

import pytest

from worker import resource_registry


def make_engine(monkeypatch, database="devtesthub"):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = database

    result = Mock()
    result.scalar_one_or_none.return_value = 1

    connection.execute.side_effect = [
        database_result,
        result,
    ]

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(
        resource_registry,
        "engine",
        fake_engine,
    )

    return connection, result


def test_register_resource(monkeypatch):
    connection, _ = make_engine(monkeypatch)

    resource_id = resource_registry.register_resource(
        environment_id=15,
        resource_type="container",
        role="api",
        resource_name="devtest-hub-env-15-api",
        docker_id="a" * 64,
    )

    assert resource_id == 1

    query, parameters = connection.execute.call_args_list[1].args

    assert "INSERT INTO environment_resources" in str(query)
    assert "e.template = 'fastapi-postgres'" in str(query)
    assert "e.status = 'deploying'" in str(query)

    assert parameters["environment_id"] == 15
    assert parameters["resource_type"] == "container"
    assert parameters["role"] == "api"


def test_register_resource_rejects_wrong_database(monkeypatch):
    make_engine(
        monkeypatch,
        database="devtesthub_test",
    )

    with pytest.raises(RuntimeError):
        resource_registry.register_resource(
            environment_id=15,
            resource_type="network",
            role="internal",
            resource_name="devtest-hub-env-15-net",
        )


def test_register_resource_rejects_invalid_docker_id():
    with pytest.raises(ValueError):
        resource_registry.register_resource(
            environment_id=15,
            resource_type="container",
            role="api",
            resource_name="devtest-hub-env-15-api",
            docker_id="invalid",
        )


def test_register_resource_requires_deploying(monkeypatch):
    _, result = make_engine(monkeypatch)

    result.scalar_one_or_none.return_value = None

    with pytest.raises(RuntimeError):
        resource_registry.register_resource(
            environment_id=15,
            resource_type="volume",
            role="postgres-data",
            resource_name="devtest-hub-env-15-data",
        )
