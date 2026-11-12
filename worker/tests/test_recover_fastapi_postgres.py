from unittest.mock import MagicMock, Mock

from docker.errors import NotFound

from worker import recover_fastapi_postgres as recovery
from worker.deploy_fastapi_postgres import get_resource_labels


ENVIRONMENT = {
    "id": 15,
    "name": "recovery-test",
}


def make_resource(name, role, docker_id=None):
    resource = MagicMock()

    resource.name = name
    resource.labels = get_resource_labels(15, role)

    if docker_id is not None:
        resource.id = docker_id
        resource.status = "running"
        resource.attrs = {
            "State": {
                "Health": {"Status": "healthy"}
            }
        }

    return resource


def test_recovery_query_filters_template(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    jobs_result = MagicMock()
    jobs_result.mappings.return_value.all.return_value = []

    connection.execute.side_effect = [
        database_result,
        jobs_result,
    ]

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(recovery, "engine", fake_engine)

    assert recovery.get_unfinished_environments() == []

    query = connection.execute.call_args_list[1].args[0]

    assert "template = 'fastapi-postgres'" in str(query)
    assert "status = 'deploying'" in str(query)


def test_recovery_detects_missing_resources(
    monkeypatch,
    capsys,
):
    client = MagicMock()

    client.networks.get.side_effect = NotFound("missing")
    client.volumes.get.side_effect = NotFound("missing")
    client.containers.get.side_effect = NotFound("missing")

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: [],
    )

    recovery.inspect_environment(client, ENVIRONMENT)

    output = capsys.readouterr().out

    assert output.count("Docker-ресурс отсутствует") == 4

    client.containers.create.assert_not_called()
    client.networks.create.assert_not_called()
    client.volumes.create.assert_not_called()


def test_recovery_detects_registered_resources(
    monkeypatch,
    capsys,
):
    client = MagicMock()

    network = make_resource(
        "devtest-hub-env-15-net",
        "network",
    )

    volume = make_resource(
        "devtest-hub-env-15-data",
        "volume",
    )

    postgres = make_resource(
        "devtest-hub-env-15-db",
        "postgres",
        "b" * 64,
    )

    api = make_resource(
        "devtest-hub-env-15-api",
        "api",
        "a" * 64,
    )

    client.networks.get.return_value = network
    client.volumes.get.return_value = volume

    client.containers.get.side_effect = [
        postgres,
        api,
    ]

    records = [
        {
            "resource_type": "network",
            "role": "network",
            "resource_name": network.name,
            "docker_id": None,
        },
        {
            "resource_type": "volume",
            "role": "volume",
            "resource_name": volume.name,
            "docker_id": None,
        },
        {
            "resource_type": "container",
            "role": "postgres",
            "resource_name": postgres.name,
            "docker_id": postgres.id,
        },
        {
            "resource_type": "container",
            "role": "api",
            "resource_name": api.name,
            "docker_id": api.id,
        },
    ]

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: records,
    )

    recovery.inspect_environment(client, ENVIRONMENT)

    output = capsys.readouterr().out

    assert output.count(
        "ресурс найден и зарегистрирован"
    ) == 4

    assert "postgres: status=running, health=healthy" in output
    assert "api: status=running, health=healthy" in output


def test_recovery_rejects_foreign_resource(
    monkeypatch,
    capsys,
):
    client = MagicMock()

    network = make_resource(
        "devtest-hub-env-15-net",
        "network",
    )

    network.labels = get_resource_labels(999, "network")

    client.networks.get.return_value = network
    client.volumes.get.side_effect = NotFound("missing")
    client.containers.get.side_effect = NotFound("missing")

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: [],
    )

    recovery.inspect_environment(client, ENVIRONMENT)

    output = capsys.readouterr().out

    assert "НЕСООТВЕТСТВИЕ принадлежности" in output

    network.remove.assert_not_called()
