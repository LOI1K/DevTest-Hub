from unittest.mock import MagicMock

from docker.errors import NotFound

from worker import recover_fastapi_postgres as recovery
from worker.deploy_fastapi_postgres import (
    get_resource_labels,
    get_resource_names,
)


ENVIRONMENT = {
    "id": 15,
    "name": "recovery-readiness-test",
}


def make_test_environment(monkeypatch):
    names = get_resource_names(15)
    network_id = "c" * 64

    network = MagicMock()
    network.name = names["network"]
    network.id = network_id
    network.labels = get_resource_labels(15, "network")

    volume = MagicMock()
    volume.name = names["volume"]
    volume.labels = get_resource_labels(15, "volume")

    postgres = MagicMock()
    postgres.name = names["postgres"]
    postgres.id = "b" * 64
    postgres.labels = get_resource_labels(15, "postgres")
    postgres.status = "running"
    postgres.attrs = {
        "State": {"Health": {"Status": "healthy"}},
        "NetworkSettings": {
            "Networks": {
                names["network"]: {"NetworkID": network_id}
            }
        },
        "Mounts": [
            {
                "Type": "volume",
                "Name": names["volume"],
                "Destination": "/var/lib/postgresql",
            }
        ],
    }

    api = MagicMock()
    api.name = names["api"]
    api.id = "a" * 64
    api.labels = get_resource_labels(15, "api")
    api.status = "running"
    api.attrs = {
        "State": {"Health": {"Status": "healthy"}},
        "NetworkSettings": {
            "Networks": {
                names["network"]: {"NetworkID": network_id}
            },
            "Ports": {
                "8000/tcp": [
                    {
                        "HostIp": "127.0.0.1",
                        "HostPort": "52586",
                    }
                ]
            },
        },
    }

    resources = {
        "network": network,
        "volume": volume,
        "postgres": postgres,
        "api": api,
    }

    client = MagicMock()
    client.networks.get.return_value = network
    client.volumes.get.return_value = volume
    client.containers.get.side_effect = (
        lambda name: postgres if name == names["postgres"] else api
    )

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: [],
    )

    return client, resources, names


def test_complete_environment_is_recoverable(monkeypatch):
    client, _, _ = make_test_environment(monkeypatch)

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is True
    assert result["api_id"] == "a" * 64
    assert result["host_port"] == 52586
    assert set(result["missing_roles"]) == {
        "network", "volume", "postgres", "api"
    }


def test_registered_environment_is_recoverable(monkeypatch):
    client, resources, names = make_test_environment(monkeypatch)

    records = []

    for resource_type, role in (
        ("network", "network"),
        ("volume", "volume"),
        ("container", "postgres"),
        ("container", "api"),
    ):
        records.append({
            "resource_type": resource_type,
            "role": role,
            "resource_name": names[role],
            "docker_id": (
                resources[role].id
                if resource_type == "container"
                else None
            ),
        })

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: records,
    )

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is True
    assert result["missing_roles"] == []


def test_missing_volume_blocks_recovery(monkeypatch):
    client, _, _ = make_test_environment(monkeypatch)

    client.volumes.get.side_effect = NotFound("missing")

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_foreign_resource_blocks_recovery(monkeypatch):
    client, resources, _ = make_test_environment(monkeypatch)

    resources["api"].labels = get_resource_labels(999, "api")

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_unhealthy_postgres_blocks_recovery(monkeypatch):
    client, resources, _ = make_test_environment(monkeypatch)

    resources["postgres"].attrs["State"]["Health"][
        "Status"
    ] = "unhealthy"

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_wrong_network_blocks_recovery(monkeypatch):
    client, resources, names = make_test_environment(monkeypatch)

    resources["api"].attrs["NetworkSettings"]["Networks"][
        names["network"]
    ]["NetworkID"] = "d" * 64

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_wrong_volume_mount_blocks_recovery(monkeypatch):
    client, resources, _ = make_test_environment(monkeypatch)

    resources["postgres"].attrs["Mounts"] = []

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_public_port_blocks_recovery(monkeypatch):
    client, resources, _ = make_test_environment(monkeypatch)

    resources["api"].attrs["NetworkSettings"]["Ports"][
        "8000/tcp"
    ][0]["HostIp"] = "0.0.0.0"

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False


def test_wrong_registered_docker_id_blocks_recovery(
    monkeypatch,
):
    client, _, names = make_test_environment(monkeypatch)

    monkeypatch.setattr(
        recovery,
        "get_environment_resources",
        lambda environment_id: [
            {
                "resource_type": "container",
                "role": "api",
                "resource_name": names["api"],
                "docker_id": "d" * 64,
            }
        ],
    )

    result = recovery.check_recovery_readiness(
        client, ENVIRONMENT
    )

    assert result["ready"] is False