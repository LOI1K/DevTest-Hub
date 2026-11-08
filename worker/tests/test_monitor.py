from unittest.mock import MagicMock, Mock

import pytest
from docker.errors import DockerException, NotFound

from worker import monitor


ENVIRONMENT = {
    "id": 3,
    "name": "my-first-nginx",
    "container_id": "a" * 64,
    "host_port": 52368,
}


@pytest.fixture
def docker_client():
    return Mock()


def make_container(
    status="running",
    managed=True,
    host_ip="127.0.0.1",
    host_port="52368",
):
    container = Mock()

    container.id = "a" * 64
    container.name = "devtest-hub-env-3"
    container.status = status

    container.labels = {
        "devtest-hub.managed": (
            "true" if managed else "false"
        ),
        "devtest-hub.environment-id": "3",
    }

    container.attrs = {
        "NetworkSettings": {
            "Ports": {
                "80/tcp": [
                    {
                        "HostIp": host_ip,
                        "HostPort": host_port,
                    }
                ]
            }
        }
    }

    return container


def test_running_container_is_ok(docker_client):
    docker_client.containers.get.return_value = (
        make_container()
    )

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert result == "OK: контейнер работает, порт 52368"


def test_missing_container(docker_client):
    docker_client.containers.get.side_effect = [
        NotFound("Container not found"),
        NotFound("Container not found"),
    ]

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "Docker-контейнер отсутствует" in result


def test_stopped_container(docker_client):
    docker_client.containers.get.return_value = (
        make_container(status="exited")
    )

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "статус exited" in result


def test_foreign_container(docker_client):
    docker_client.containers.get.return_value = (
        make_container(managed=False)
    )

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "не прошёл проверку принадлежности" in result


def test_wrong_port(docker_client):
    docker_client.containers.get.return_value = (
        make_container(host_port="59999")
    )

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "порт Docker не совпадает" in result


def test_unsafe_host_binding(docker_client):
    docker_client.containers.get.return_value = (
        make_container(host_ip="0.0.0.0")
    )

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "порт Docker не совпадает" in result


def test_missing_metadata(docker_client):
    environment = ENVIRONMENT.copy()
    environment["container_id"] = None

    result = monitor.check_environment(
        docker_client,
        environment,
    )

    assert "отсутствуют корректные Docker-метаданные" in result

    docker_client.containers.get.assert_not_called()


def test_different_container_id(docker_client):
    docker_client.containers.get.side_effect = [
        NotFound("Original container not found"),
        make_container(),
    ]

    result = monitor.check_environment(
        docker_client,
        ENVIRONMENT.copy(),
    )

    assert "другим Docker ID" in result


def test_docker_connection_error(docker_client):
    docker_client.containers.get.side_effect = (
        DockerException("Docker unavailable")
    )

    with pytest.raises(DockerException):
        monitor.check_environment(
            docker_client,
            ENVIRONMENT.copy(),
        )


def test_monitor_main(monkeypatch, capsys):
    client = Mock()
    client.ping.return_value = True

    client.containers.get.return_value = (
        make_container()
    )

    monkeypatch.setattr(
        monitor,
        "get_running_environments",
        lambda: [ENVIRONMENT.copy()],
    )

    monkeypatch.setattr(
        monitor.docker,
        "from_env",
        lambda: client,
    )

    monitor.main()

    output = capsys.readouterr().out

    assert "my-first-nginx" in output
    assert "OK: контейнер работает" in output

    client.close.assert_called_once()


def test_mark_failed_updates_running_environment(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.rowcount = 1

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(monitor, "engine", fake_engine)

    result = monitor.mark_failed(ENVIRONMENT.copy())

    assert result is True

    query, params = connection.execute.call_args.args

    assert "status = 'running'" in str(query)
    assert "container_id = :container_id" in str(query)
    assert "host_port = :host_port" in str(query)

    assert params == {
        "id": 3,
        "container_id": "a" * 64,
        "host_port": 52368,
    }


def test_mark_failed_skips_changed_environment(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.rowcount = 0

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(monitor, "engine", fake_engine)

    result = monitor.mark_failed(ENVIRONMENT.copy())

    assert result is False


@pytest.fixture
def monitoring_mocks(monkeypatch):
    client = Mock()
    client.ping.return_value = True

    update = Mock(return_value=True)

    monkeypatch.setattr(
        monitor,
        "get_running_environments",
        lambda: [ENVIRONMENT.copy()],
    )

    monkeypatch.setattr(
        monitor.docker,
        "from_env",
        lambda: client,
    )

    monkeypatch.setattr(
        monitor,
        "mark_failed",
        update,
    )

    return client, update


def test_dry_run_does_not_update_database(
    monitoring_mocks,
    monkeypatch,
):
    client, update = monitoring_mocks

    check = Mock(
        return_value="ОШИБКА: Docker-контейнер имеет статус exited"
    )

    monkeypatch.setattr(monitor, "check_environment", check)

    monitor.main(apply=False)

    update.assert_not_called()
    assert check.call_count == 1
    client.close.assert_called_once()


def test_apply_marks_stopped_container_failed(
    monitoring_mocks,
    monkeypatch,
):
    client, update = monitoring_mocks

    check = Mock(
        return_value="ОШИБКА: Docker-контейнер имеет статус exited"
    )

    monkeypatch.setattr(monitor, "check_environment", check)

    monitor.main(apply=True)

    assert check.call_count == 2
    update.assert_called_once_with(ENVIRONMENT.copy())
    client.close.assert_called_once()


def test_apply_skips_container_that_started_again(
    monitoring_mocks,
    monkeypatch,
):
    _, update = monitoring_mocks

    check = Mock(
        side_effect=[
            "ОШИБКА: Docker-контейнер имеет статус exited",
            "OK: контейнер работает, порт 52368",
        ]
    )

    monkeypatch.setattr(monitor, "check_environment", check)

    monitor.main(apply=True)

    assert check.call_count == 2
    update.assert_not_called()


def test_apply_skips_ownership_mismatch(
    monitoring_mocks,
    monkeypatch,
):
    _, update = monitoring_mocks

    check = Mock(
        return_value=(
            "НЕСООТВЕТСТВИЕ: контейнер не прошёл "
            "проверку принадлежности"
        )
    )

    monkeypatch.setattr(monitor, "check_environment", check)

    monitor.main(apply=True)

    update.assert_not_called()
    assert check.call_count == 1


def test_docker_unavailable_does_not_update_database(
    monitoring_mocks,
):
    client, update = monitoring_mocks
    client.ping.return_value = False

    with pytest.raises(
        RuntimeError,
        match="Docker Engine недоступен",
    ):
        monitor.main(apply=True)

    update.assert_not_called()
    client.close.assert_called_once()
