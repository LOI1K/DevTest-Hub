from unittest.mock import MagicMock, Mock

import pytest

from worker import monitor


ENVIRONMENT = {
    "id": 999,
    "name": "port-recovery-test",
    "container_id": "a" * 64,
    "host_port": 52368,
}

PORT_MISMATCH = (
    "НЕСООТВЕТСТВИЕ: порт Docker не совпадает с PostgreSQL"
)


def make_docker_client():
    container = MagicMock()

    container.id = ENVIRONMENT["container_id"]
    container.name = "devtest-hub-env-999"
    container.status = "running"

    container.labels = {
        "devtest-hub.managed": "true",
        "devtest-hub.environment-id": "999",
    }

    container.attrs = {
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [
                    {
                        "HostIp": "127.0.0.1",
                        "HostPort": "55731",
                    }
                ]
            }
        }
    }

    client = MagicMock()
    client.ping.return_value = True
    client.containers.get.return_value = container

    return client, container


def setup_monitor(monkeypatch):
    client, _ = make_docker_client()

    monkeypatch.setattr(
        monitor.docker,
        "from_env",
        lambda: client,
    )

    monkeypatch.setattr(
        monitor,
        "get_running_environments",
        lambda: [dict(ENVIRONMENT)],
    )

    monkeypatch.setattr(
        monitor,
        "check_environment",
        lambda client, environment: PORT_MISMATCH,
    )

    return client


def test_verified_port_is_detected():
    client, _ = make_docker_client()

    result = monitor.get_verified_port(
        client,
        ENVIRONMENT,
    )

    assert result == 55731


@pytest.mark.parametrize(
    "invalid_property",
    [
        "docker_id",
        "container_name",
        "managed_label",
        "container_status",
        "host_ip",
        "invalid_port",
    ],
)
def test_unsafe_container_is_rejected(invalid_property):
    client, container = make_docker_client()

    if invalid_property == "docker_id":
        container.id = "b" * 64

    elif invalid_property == "container_name":
        container.name = "another-container"

    elif invalid_property == "managed_label":
        container.labels["devtest-hub.managed"] = "false"

    elif invalid_property == "container_status":
        container.status = "exited"

    elif invalid_property == "host_ip":
        container.attrs["NetworkSettings"]["Ports"]["80/tcp"][0][
            "HostIp"
        ] = "0.0.0.0"

    elif invalid_property == "invalid_port":
        container.attrs["NetworkSettings"]["Ports"]["80/tcp"][0][
            "HostPort"
        ] = "99999"

    assert monitor.get_verified_port(
        client,
        ENVIRONMENT,
    ) is None


def test_dry_run_does_not_change_database(monkeypatch, capsys):
    setup_monitor(monkeypatch)

    monkeypatch.setattr(
        monitor,
        "get_verified_port",
        Mock(return_value=55731),
    )

    update = Mock()
    monkeypatch.setattr(monitor, "update_host_port", update)

    monitor.main(apply=False)

    output = capsys.readouterr().out

    assert "52368 -> 55731" in output
    update.assert_not_called()


def test_apply_updates_verified_port(monkeypatch):
    setup_monitor(monkeypatch)

    verify = Mock(side_effect=[55731, 55731])
    update = Mock(return_value=True)

    monkeypatch.setattr(
        monitor,
        "get_verified_port",
        verify,
    )

    monkeypatch.setattr(
        monitor,
        "update_host_port",
        update,
    )

    monitor.main(apply=True)

    assert verify.call_count == 2
    update.assert_called_once_with(
        ENVIRONMENT,
        55731,
    )


def test_changed_port_prevents_update(monkeypatch):
    setup_monitor(monkeypatch)

    verify = Mock(side_effect=[55731, 55999])
    update = Mock()

    monkeypatch.setattr(
        monitor,
        "get_verified_port",
        verify,
    )

    monkeypatch.setattr(
        monitor,
        "update_host_port",
        update,
    )

    monitor.main(apply=True)

    update.assert_not_called()


def test_database_update_is_conditional(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.rowcount = 1

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(
        monitor,
        "engine",
        fake_engine,
    )

    result = monitor.update_host_port(
        ENVIRONMENT,
        55731,
    )

    assert result is True

    query, parameters = connection.execute.call_args.args

    sql = str(query)

    assert "template = 'nginx'" in sql
    assert "status = 'running'" in sql
    assert "container_id = :container_id" in sql
    assert "host_port = :old_port" in sql

    assert parameters["id"] == 999
    assert parameters["old_port"] == 52368
    assert parameters["new_port"] == 55731