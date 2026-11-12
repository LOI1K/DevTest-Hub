import pytest


from unittest.mock import MagicMock, Mock

from docker.errors import DockerException

from worker import monitor_fastapi_postgres as monitor


ENVIRONMENT = {
    "id": 15,
    "name": "monitor-test",
    "template": "fastapi-postgres",
    "status": "running",
    "container_id": "a" * 64,
    "host_port": 52586,
}


def healthy_result(**changes):
    result = {
        "ready": True,
        "reason": "Все ресурсы исправны",
        "api_id": "a" * 64,
        "postgres_id": "b" * 64,
        "host_port": 52586,
        "missing_roles": [],
    }
    result.update(changes)
    return result


def test_monitor_query_filters_template(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    rows_result = MagicMock()
    rows_result.mappings.return_value.all.return_value = [
        ENVIRONMENT
    ]

    connection.execute.side_effect = [
        database_result,
        rows_result,
    ]

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(
        monitor,
        "engine",
        fake_engine,
    )

    environments = monitor.get_running_environments()

    assert environments == [ENVIRONMENT]

    sql = str(connection.execute.call_args_list[1].args[0])

    assert "template = 'fastapi-postgres'" in sql
    assert "status = 'running'" in sql

    fake_engine.begin.assert_not_called()


def test_healthy_environment(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(return_value=healthy_result()),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "healthy"
    assert result["actual_port"] == 52586


def test_port_change_detected(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(return_value=healthy_result(host_port=53000)),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "port_changed"
    assert result["actual_port"] == 53000


def test_wrong_api_id_is_degraded(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(return_value=healthy_result(api_id="f" * 64)),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "degraded"


def test_missing_registry_records_are_degraded(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(return_value=healthy_result(
            missing_roles=["volume"],
        )),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "degraded"
    assert "volume" in result["reason"]


def test_unhealthy_postgres_is_degraded(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(return_value={
            "ready": False,
            "reason": "postgres: контейнер не готов",
        }),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "degraded"
    assert "postgres" in result["reason"]


def test_docker_error_is_unknown(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "check_recovery_readiness",
        Mock(side_effect=DockerException(
            "Docker Engine unavailable"
        )),
    )

    result = monitor.inspect_running_environment(
        MagicMock(),
        ENVIRONMENT,
    )

    assert result["state"] == "unknown"


def test_no_environments_skips_docker(monkeypatch):
    monkeypatch.setattr(
        monitor,
        "get_running_environments",
        lambda: [],
    )

    docker_from_env = Mock()

    monkeypatch.setattr(
        monitor.docker,
        "from_env",
        docker_from_env,
    )

    assert monitor.main() == 0

    docker_from_env.assert_not_called()


def test_update_port_is_conditional(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    update_result = Mock()
    update_result.rowcount = 1

    connection.execute.side_effect = [
        database_result,
        update_result,
    ]

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(monitor, "engine", fake_engine)

    assert monitor.update_host_port(
        ENVIRONMENT,
        53000,
    ) is True

    query, parameters = connection.execute.call_args_list[1].args
    sql = str(query)

    assert "template = 'fastapi-postgres'" in sql
    assert "status = 'running'" in sql
    assert "owner_id IS NOT NULL" in sql
    assert "container_id = :container_id" in sql
    assert "host_port = :old_port" in sql

    assert parameters["environment_id"] == 15
    assert parameters["old_port"] == 52586
    assert parameters["new_port"] == 53000


def test_update_port_rejects_wrong_database(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = (
        "devtesthub_test"
    )

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(monitor, "engine", fake_engine)

    with pytest.raises(RuntimeError):
        monitor.update_host_port(ENVIRONMENT, 53000)

    assert connection.execute.call_count == 1


def prepare_main_monitor(monkeypatch, inspection):
    client = MagicMock()

    monkeypatch.setattr(
        monitor,
        "get_running_environments",
        lambda: [ENVIRONMENT],
    )

    monkeypatch.setattr(
        monitor.docker,
        "from_env",
        Mock(return_value=client),
    )

    inspect = Mock(side_effect=inspection)

    monkeypatch.setattr(
        monitor,
        "inspect_running_environment",
        inspect,
    )

    update = Mock(return_value=True)

    monkeypatch.setattr(
        monitor,
        "update_host_port",
        update,
    )

    return client, inspect, update


def port_changed_result(port):
    return {
        "state": "port_changed",
        "reason": "Порт Docker изменился",
        "actual_port": port,
    }


def test_monitor_dry_run_never_updates_port(monkeypatch):
    client, inspect, update = prepare_main_monitor(
        monkeypatch,
        [port_changed_result(53000)],
    )

    assert monitor.main() == 0

    assert inspect.call_count == 1
    update.assert_not_called()
    client.close.assert_called_once()


def test_monitor_updates_confirmed_port(monkeypatch):
    client, inspect, update = prepare_main_monitor(
        monkeypatch,
        [
            port_changed_result(53000),
            port_changed_result(53000),
        ],
    )

    assert monitor.main(apply=True) == 0

    assert inspect.call_count == 2
    update.assert_called_once_with(
        ENVIRONMENT,
        53000,
    )

    client.close.assert_called_once()


def test_monitor_rejects_unstable_port(monkeypatch):
    _, inspect, update = prepare_main_monitor(
        monkeypatch,
        [
            port_changed_result(53000),
            port_changed_result(54000),
        ],
    )

    assert monitor.main(apply=True) == 0

    assert inspect.call_count == 2
    update.assert_not_called()
