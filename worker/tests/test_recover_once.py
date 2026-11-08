from unittest.mock import Mock

import pytest
from docker.errors import NotFound

from worker import recover_once


JOB = {
    "id": 10,
    "name": "recovery-test-01",
    "container_id": None,
    "host_port": None,
}


@pytest.fixture
def mocked_worker(monkeypatch):
    client = Mock()
    client.ping.return_value = True

    update = Mock(return_value=True)

    monkeypatch.setattr(
        recover_once,
        "get_unfinished_jobs",
        lambda: [JOB.copy()],
    )
    monkeypatch.setattr(
        recover_once.docker,
        "from_env",
        lambda: client,
    )
    monkeypatch.setattr(
        recover_once,
        "update_job",
        update,
    )

    return client, update


def make_container(host_ip="127.0.0.1", managed=True):
    container = Mock()

    container.id = "a" * 64
    container.name = "devtest-hub-env-10"
    container.status = "running"

    container.labels = {
        "devtest-hub.managed": "true" if managed else "false",
        "devtest-hub.environment-id": "10",
    }

    container.attrs = {
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [
                    {
                        "HostIp": host_ip,
                        "HostPort": "64860",
                    }
                ]
            }
        }
    }

    return container


def test_no_unfinished_jobs(monkeypatch):
    monkeypatch.setattr(
        recover_once,
        "get_unfinished_jobs",
        lambda: [],
    )

    docker_mock = Mock()
    monkeypatch.setattr(
        recover_once.docker,
        "from_env",
        docker_mock,
    )

    recover_once.recover_jobs(apply=False)

    docker_mock.assert_not_called()


def test_missing_container_dry_run(mocked_worker):
    client, update = mocked_worker

    client.containers.get.side_effect = NotFound(
        "Container not found"
    )

    recover_once.recover_jobs(apply=False)

    update.assert_not_called()


def test_missing_container_apply(mocked_worker):
    client, update = mocked_worker

    client.containers.get.side_effect = NotFound(
        "Container not found"
    )

    recover_once.recover_jobs(apply=True)

    update.assert_called_once_with(10, "failed")


def test_running_container_recovery(mocked_worker):
    client, update = mocked_worker

    client.containers.get.return_value = make_container()

    recover_once.recover_jobs(apply=True)

    update.assert_called_once_with(
        10,
        "running",
        container_id="a" * 64,
        host_port=64860,
    )

    client.close.assert_called_once()


def test_foreign_container_is_skipped(mocked_worker):
    client, update = mocked_worker

    client.containers.get.return_value = make_container(
        managed=False
    )

    recover_once.recover_jobs(apply=True)

    update.assert_not_called()


def test_unsafe_port_binding_is_skipped(mocked_worker):
    client, update = mocked_worker

    client.containers.get.return_value = make_container(
        host_ip="0.0.0.0"
    )

    recover_once.recover_jobs(apply=True)

    update.assert_not_called()
