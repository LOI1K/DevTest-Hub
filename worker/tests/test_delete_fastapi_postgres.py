from unittest.mock import MagicMock, call

import pytest
from docker.errors import NotFound

from worker.delete_fastapi_postgres import (
    build_deletion_plan,
    delete_registered_resources,
)
from worker.deploy_fastapi_postgres import (
    get_resource_labels,
    get_resource_names,
)


def make_objects():
    names = get_resource_names(15)
    client = MagicMock()

    resources = {}

    for role in ("api", "postgres", "network", "volume"):
        resource = MagicMock()
        resource.name = names[role]
        resource.labels = get_resource_labels(15, role)

        if role == "api":
            resource.id = "a" * 64
        elif role == "postgres":
            resource.id = "b" * 64

        if role in {"api", "postgres"}:
            resource.status = "running"

        resource.attrs = {"Containers": {}}
        resources[role] = resource

    client.containers.get.side_effect = (
        lambda name: resources[
            "api" if name == names["api"] else "postgres"
        ]
    )
    client.networks.get.return_value = resources["network"]
    client.volumes.get.return_value = resources["volume"]

    records = []

    for role in ("api", "postgres", "network", "volume"):
        records.append({
            "role": role,
            "resource_type": (
                "container"
                if role in {"api", "postgres"}
                else role
            ),
            "resource_name": names[role],
            "docker_id": (
                resources[role].id
                if role in {"api", "postgres"}
                else None
            ),
        })

    return client, resources, records


def test_valid_deletion_plan():
    client, resources, records = make_objects()

    registered, found = build_deletion_plan(
        client, 15, records
    )

    assert len(registered) == 4
    assert found == resources


def test_missing_registry_record_is_rejected():
    client, _, records = make_objects()

    with pytest.raises(RuntimeError, match="четыре ресурса"):
        build_deletion_plan(client, 15, records[:-1])


def test_foreign_resource_is_rejected():
    client, resources, records = make_objects()

    resources["api"].labels = get_resource_labels(999, "api")

    with pytest.raises(
        RuntimeError,
        match="не принадлежит",
    ):
        build_deletion_plan(client, 15, records)


def test_wrong_container_id_is_rejected():
    client, _, records = make_objects()

    records[0]["docker_id"] = "f" * 64

    with pytest.raises(
        RuntimeError,
        match="Не совпадает Docker ID",
    ):
        build_deletion_plan(client, 15, records)


def test_foreign_network_connection_blocks_deletion():
    client, resources, records = make_objects()

    resources["network"].attrs["Containers"] = {
        "f" * 64: {"Name": "foreign-container"},
    }

    with pytest.raises(
        RuntimeError,
        match="посторонние контейнеры",
    ):
        delete_registered_resources(
            client, 15, records, delete_volume=True
        )

    for resource in resources.values():
        resource.remove.assert_not_called()


def test_default_deletion_preserves_volume():
    client, resources, records = make_objects()

    removed = delete_registered_resources(
        client, 15, records
    )

    assert removed == ["api", "postgres", "network"]

    resources["api"].stop.assert_called_once_with(timeout=10)
    resources["postgres"].stop.assert_called_once_with(timeout=10)

    resources["api"].remove.assert_called_once_with(v=False)
    resources["postgres"].remove.assert_called_once_with(v=False)
    resources["network"].remove.assert_called_once()

    resources["volume"].remove.assert_not_called()


def test_explicit_deletion_removes_volume_last():
    client, resources, records = make_objects()

    order = []

    for role, resource in resources.items():
        resource.remove.side_effect = (
            lambda *args, role=role, **kwargs: order.append(role)
        )

    removed = delete_registered_resources(
        client,
        15,
        records,
        delete_volume=True,
    )

    assert removed == [
        "api", "postgres", "network", "volume"
    ]

    assert order == [
        "api", "postgres", "network", "volume"
    ]

    resources["volume"].remove.assert_called_once_with(
        force=False
    )


def test_container_error_preserves_other_resources():
    client, resources, records = make_objects()

    resources["api"].remove.side_effect = RuntimeError(
        "Docker error"
    )

    with pytest.raises(RuntimeError, match="Docker error"):
        delete_registered_resources(
            client, 15, records, delete_volume=True
        )

    resources["postgres"].remove.assert_not_called()
    resources["network"].remove.assert_not_called()
    resources["volume"].remove.assert_not_called()


def test_already_missing_resources_are_skipped():
    client, resources, records = make_objects()

    client.containers.get.side_effect = NotFound("missing")
    client.networks.get.side_effect = NotFound("missing")
    client.volumes.get.side_effect = NotFound("missing")

    removed = delete_registered_resources(
        client,
        15,
        records,
        delete_volume=True,
    )

    assert removed == []

    for resource in resources.values():
        resource.remove.assert_not_called()
