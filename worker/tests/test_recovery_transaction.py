from unittest.mock import MagicMock, Mock

import pytest

from worker import recover_fastapi_postgres as recovery


def prepare_database(monkeypatch, exists=True, update_count=1):
    connection = MagicMock()
    operations = []

    def execute(query, parameters=None):
        sql = str(query)

        if "SELECT current_database()" in sql:
            result = Mock()
            result.scalar_one.return_value = "devtesthub"
            return result

        if "FOR UPDATE" in sql:
            result = MagicMock()
            result.mappings.return_value.first.return_value = (
                {"id": 15, "name": "recovery-test"}
                if exists else None
            )
            return result

        if "UPDATE environments" in sql:
            operations.append(("update", parameters))
            return Mock(rowcount=update_count)

        if "INSERT INTO environment_resources" in sql:
            operations.append(("insert", parameters))
            return Mock(rowcount=1)

        if "FROM environment_resources" in sql and "SELECT" in sql:
            result = MagicMock()
            result.mappings.return_value.all.return_value = []
            return result

        raise AssertionError(f"Неожиданный SQL: {sql}")

    connection.execute.side_effect = execute

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(recovery, "engine", fake_engine)

    return operations


def ready_result(missing_roles=None):
    if missing_roles is None:
        missing_roles = [
            "network", "volume", "postgres", "api"
        ]

    return {
        "ready": True,
        "reason": "OK",
        "api_id": "a" * 64,
        "postgres_id": "b" * 64,
        "host_port": 52586,
        "missing_roles": missing_roles,
    }


def test_recovery_registers_resources_and_updates_status(monkeypatch):
    operations = prepare_database(monkeypatch)

    monkeypatch.setattr(
        recovery,
        "check_recovery_readiness",
        Mock(return_value=ready_result()),
    )

    result = recovery.recover_ready_environment(
        MagicMock(), 15
    )

    assert result is True
    assert [operation for operation, _ in operations] == [
        "insert", "insert", "insert", "insert", "update"
    ]

    assert operations[-1][1]["host_port"] == 52586
    assert operations[-1][1]["api_id"] == "a" * 64


def test_recovery_does_not_duplicate_registered_resources(
    monkeypatch,
):
    operations = prepare_database(monkeypatch)

    monkeypatch.setattr(
        recovery,
        "check_recovery_readiness",
        Mock(return_value=ready_result([])),
    )

    assert recovery.recover_ready_environment(
        MagicMock(), 15
    ) is True

    assert len(operations) == 1
    assert operations[0][0] == "update"


def test_unready_environment_is_not_modified(monkeypatch):
    operations = prepare_database(monkeypatch)

    monkeypatch.setattr(
        recovery,
        "check_recovery_readiness",
        Mock(return_value={
            "ready": False,
            "reason": "PostgreSQL не готова",
        }),
    )

    result = recovery.recover_ready_environment(
        MagicMock(), 15
    )

    assert result is False
    assert operations == []


def test_changed_environment_is_not_modified(monkeypatch):
    operations = prepare_database(
        monkeypatch,
        exists=False,
    )

    check = Mock()
    monkeypatch.setattr(
        recovery,
        "check_recovery_readiness",
        check,
    )

    result = recovery.recover_ready_environment(
        MagicMock(), 15
    )

    assert result is False
    assert operations == []
    check.assert_not_called()


def test_failed_final_update_raises(monkeypatch):
    operations = prepare_database(
        monkeypatch,
        update_count=0,
    )

    monkeypatch.setattr(
        recovery,
        "check_recovery_readiness",
        Mock(return_value=ready_result()),
    )

    with pytest.raises(
        RuntimeError,
        match="Не удалось завершить восстановление",
    ):
        recovery.recover_ready_environment(
            MagicMock(), 15
        )

    assert operations[-1][0] == "update"
