from unittest.mock import MagicMock, Mock

import pytest
from docker.errors import NotFound

from worker import delete_once


@pytest.fixture
def docker_client(monkeypatch):
    client = Mock()

    monkeypatch.setattr(
        delete_once.docker,
        "from_env",
        lambda: client,
    )

    return client


def make_container(managed=True, status="running"):
    container = Mock()

    container.name = "devtest-hub-env-10"
    container.status = status
    container.labels = {
        "devtest-hub.managed": "true" if managed else "false",
        "devtest-hub.environment-id": "10",
    }

    return container


def test_missing_container(docker_client):
    docker_client.containers.get.side_effect = NotFound(
        "Container not found"
    )

    delete_once.cleanup_container_without_metadata(
        10, apply=True
    )

    docker_client.containers.get.assert_called_once_with(
        "devtest-hub-env-10"
    )
    docker_client.close.assert_called_once()


def test_dry_run_does_not_delete(docker_client):
    container = make_container()
    docker_client.containers.get.return_value = container

    delete_once.cleanup_container_without_metadata(
        10, apply=False
    )

    container.stop.assert_not_called()
    container.remove.assert_not_called()


def test_managed_container_is_deleted(docker_client):
    container = make_container()
    docker_client.containers.get.return_value = container

    delete_once.cleanup_container_without_metadata(
        10, apply=True
    )

    container.stop.assert_called_once_with(timeout=10)
    container.remove.assert_called_once()
    docker_client.close.assert_called_once()


def test_foreign_container_is_protected(docker_client):
    container = make_container(managed=False)
    docker_client.containers.get.return_value = container

    with pytest.raises(
        RuntimeError,
        match="не прошёл проверку принадлежности",
    ):
        delete_once.cleanup_container_without_metadata(
            10, apply=True
        )

    container.stop.assert_not_called()
    container.remove.assert_not_called()


def test_stopped_container_is_removed(docker_client):
    container = make_container(status="exited")
    docker_client.containers.get.return_value = container

    delete_once.cleanup_container_without_metadata(
        10, apply=True
    )

    container.stop.assert_not_called()
    container.remove.assert_called_once()


def test_delete_without_container_metadata(monkeypatch):
    environment = {
        "id": 10,
        "name": "recovery-missing-test-01",
        "status": "deleting",
        "container_id": None,
        "host_port": None,
    }

    connection = MagicMock()
    connection.execute.side_effect = [
        Mock(
            scalar_one=Mock(return_value="devtesthub")
        ),
        Mock(
            mappings=Mock(
                return_value=Mock(
                    first=Mock(return_value=environment)
                )
            )
        ),
        Mock(rowcount=1),
    ]

    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = (
        connection
    )

    cleanup = Mock()

    monkeypatch.setattr(delete_once, "engine", engine)
    monkeypatch.setattr(
        delete_once,
        "cleanup_container_without_metadata",
        cleanup,
    )

    delete_once.delete_environment(10, apply=True)

    cleanup.assert_called_once_with(10, True)

    delete_query = str(
        connection.execute.call_args_list[2].args[0]
    )
    assert "DELETE FROM environments" in delete_query
