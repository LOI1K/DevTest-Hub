from unittest.mock import MagicMock, Mock
from docker.errors import NotFound

import pytest

from worker import delete_fastapi_postgres_once as deletion


def prepare_deletion(
    monkeypatch,
    *,
    exists=True,
    database="devtesthub",
    final_id=15,
    empty_registry=False,
):
    connection = MagicMock()
    executed = []

    records = [
        {
            "resource_type": resource_type,
            "role": role,
            "resource_name": f"resource-{role}",
            "docker_id": None,
        }
        for resource_type, role in (
            ("container", "api"),
            ("container", "postgres"),
            ("network", "network"),
            ("volume", "volume"),
        )
    ]

    if empty_registry:
        records = []


    def execute(query, parameters=None):
        sql = str(query)
        executed.append(sql)

        if "SELECT current_database()" in sql:
            result = Mock()
            result.scalar_one.return_value = database
            return result

        if "FOR UPDATE SKIP LOCKED" in sql:
            result = MagicMock()
            result.mappings.return_value.first.return_value = (
                {"id": 15, "name": "delete-test"}
                if exists else None
            )
            return result

        if "DELETE FROM environments" in sql:
            result = Mock()
            result.scalar_one_or_none.return_value = final_id
            return result

        if "FROM environment_resources" in sql:
            result = MagicMock()
            result.mappings.return_value.all.return_value = records
            return result

        raise AssertionError(f"Неожиданный SQL: {sql}")

    connection.execute.side_effect = execute

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(deletion, "engine", fake_engine)

    client = MagicMock()
    client.ping.return_value = True

    monkeypatch.setattr(
        deletion.docker,
        "from_env",
        Mock(return_value=client),
    )

    plan = Mock(return_value=({}, {}))
    remove = Mock(return_value=[
        "api", "postgres", "network", "volume"
    ])

    monkeypatch.setattr(
        deletion, "build_deletion_plan", plan
    )
    monkeypatch.setattr(
        deletion, "delete_registered_resources", remove
    )

    return client, executed, plan, remove


def test_dry_run_does_not_delete(monkeypatch):
    client, executed, plan, remove = prepare_deletion(
        monkeypatch
    )

    assert deletion.delete_fastapi_environment(15) is True

    plan.assert_called_once()
    remove.assert_not_called()

    assert not any(
        "DELETE FROM environments" in sql
        for sql in executed
    )

    client.close.assert_called_once()


def test_apply_requires_volume_permission(monkeypatch):
    _, executed, _, remove = prepare_deletion(monkeypatch)

    with pytest.raises(
        RuntimeError,
        match="delete_volume=True",
    ):
        deletion.delete_fastapi_environment(
            15,
            apply=True,
        )

    assert executed == []
    remove.assert_not_called()


def test_full_deletion_requires_deleting_status(monkeypatch):
    client, executed, _, remove = prepare_deletion(
        monkeypatch,
        exists=False,
    )

    assert deletion.delete_fastapi_environment(
        15,
        apply=True,
        delete_volume=True,
    ) is False

    select_sql = next(
        sql for sql in executed
        if "FOR UPDATE SKIP LOCKED" in sql
    )

    assert "status = 'deleting'" in select_sql
    assert "template = 'fastapi-postgres'" in select_sql
    assert "owner_id IS NOT NULL" in select_sql

    remove.assert_not_called()
    client.close.assert_not_called()


def test_successful_full_deletion(monkeypatch):
    client, executed, plan, remove = prepare_deletion(
        monkeypatch
    )

    assert deletion.delete_fastapi_environment(
        15,
        apply=True,
        delete_volume=True,
    ) is True

    plan.assert_called_once()

    remove.assert_called_once()
    assert remove.call_args.kwargs["delete_volume"] is True

    assert any(
        "DELETE FROM environments" in sql
        for sql in executed
    )

    client.close.assert_called_once()


def test_docker_error_keeps_database_record(monkeypatch):
    client, executed, _, remove = prepare_deletion(
        monkeypatch
    )

    remove.side_effect = RuntimeError("Docker error")

    with pytest.raises(RuntimeError, match="Docker error"):
        deletion.delete_fastapi_environment(
            15,
            apply=True,
            delete_volume=True,
        )

    assert not any(
        "DELETE FROM environments" in sql
        for sql in executed
    )

    client.close.assert_called_once()


def test_wrong_database_blocks_deletion(monkeypatch):
    client, executed, _, remove = prepare_deletion(
        monkeypatch,
        database="devtesthub_test",
    )

    with pytest.raises(
        RuntimeError,
        match="основная база",
    ):
        deletion.delete_fastapi_environment(
            15,
            apply=True,
            delete_volume=True,
        )

    assert len(executed) == 1
    remove.assert_not_called()
    client.close.assert_not_called()


def test_empty_registry_can_be_deleted(monkeypatch):
    client, executed, plan, remove = prepare_deletion(
        monkeypatch,
        empty_registry=True,
    )

    client.containers.get.side_effect = NotFound("missing")
    client.networks.get.side_effect = NotFound("missing")
    client.volumes.get.side_effect = NotFound("missing")

    assert deletion.delete_fastapi_environment(
        15,
        apply=True,
        delete_volume=True,
    ) is True

    plan.assert_not_called()
    remove.assert_not_called()

    assert any(
        "DELETE FROM environments" in sql
        for sql in executed
    )


def test_unregistered_docker_resource_blocks_deletion(
    monkeypatch,
):
    client, executed, plan, remove = prepare_deletion(
        monkeypatch,
        empty_registry=True,
    )

    with pytest.raises(
        RuntimeError,
        match="незарегистрированный ресурс",
    ):
        deletion.delete_fastapi_environment(
            15,
            apply=True,
            delete_volume=True,
        )

    plan.assert_not_called()
    remove.assert_not_called()

    assert not any(
        "DELETE FROM environments" in sql
        for sql in executed
    )


def test_worker_requires_saved_volume_confirmation(
    monkeypatch,
):
    _, executed, _, _ = prepare_deletion(monkeypatch)

    assert deletion.delete_fastapi_environment(
        15,
        apply=True,
        delete_volume=True,
    ) is True

    select_sql = next(
        sql for sql in executed
        if "FOR UPDATE SKIP LOCKED" in sql
    )

    assert "delete_volume_on_delete IS TRUE" in select_sql
    assert "template = 'fastapi-postgres'" in select_sql
    assert "status = 'deleting'" in select_sql
