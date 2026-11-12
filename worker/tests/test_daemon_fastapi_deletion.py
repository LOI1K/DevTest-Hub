from unittest.mock import MagicMock, Mock

import pytest

from worker import daemon


def test_deletion_query_requires_confirmation(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    jobs_result = MagicMock()
    jobs_result.scalars.return_value.all.return_value = [
        15, 16
    ]

    connection.execute.side_effect = [
        database_result,
        jobs_result,
    ]

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(daemon, "engine", fake_engine)

    assert daemon.get_fastapi_deleting_ids() == [15, 16]

    sql = str(connection.execute.call_args_list[1].args[0])

    assert "template = 'fastapi-postgres'" in sql
    assert "status = 'deleting'" in sql
    assert "owner_id IS NOT NULL" in sql
    assert "delete_volume_on_delete IS TRUE" in sql


def test_deletion_query_rejects_wrong_database(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = (
        "devtesthub_test"
    )

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(daemon, "engine", fake_engine)

    with pytest.raises(RuntimeError):
        daemon.get_fastapi_deleting_ids()

    assert connection.execute.call_count == 1


def test_disabled_template_skips_deletions(monkeypatch):
    query = Mock()
    deletion = Mock()

    monkeypatch.setattr(
        daemon, "fastapi_enabled", lambda: False
    )
    monkeypatch.setattr(
        daemon, "get_fastapi_deleting_ids", query
    )
    monkeypatch.setattr(
        daemon, "delete_fastapi_environment", deletion
    )

    daemon.process_fastapi_deletions()

    query.assert_not_called()
    deletion.assert_not_called()


def test_enabled_template_deletes_confirmed_jobs(monkeypatch):
    deletion = Mock(return_value=True)

    monkeypatch.setattr(
        daemon, "fastapi_enabled", lambda: True
    )
    monkeypatch.setattr(
        daemon,
        "get_fastapi_deleting_ids",
        lambda: [15, 16],
    )
    monkeypatch.setattr(
        daemon, "delete_fastapi_environment", deletion
    )

    daemon.process_fastapi_deletions()

    assert deletion.call_count == 2

    deletion.assert_any_call(
        15,
        apply=True,
        delete_volume=True,
    )
    deletion.assert_any_call(
        16,
        apply=True,
        delete_volume=True,
    )


def test_deletion_error_does_not_block_next_job(monkeypatch):
    deletion = Mock(
        side_effect=[
            RuntimeError("Docker unavailable"),
            True,
        ]
    )

    monkeypatch.setattr(
        daemon, "fastapi_enabled", lambda: True
    )
    monkeypatch.setattr(
        daemon,
        "get_fastapi_deleting_ids",
        lambda: [15, 16],
    )
    monkeypatch.setattr(
        daemon, "delete_fastapi_environment", deletion
    )

    daemon.process_fastapi_deletions()

    assert deletion.call_count == 2


def test_main_job_loop_calls_fastapi_deletion_handler(
    monkeypatch,
):
    handler = Mock()

    monkeypatch.setattr(
        daemon, "get_jobs", lambda: ([], False)
    )
    monkeypatch.setattr(
        daemon, "fastapi_enabled", lambda: False
    )
    monkeypatch.setattr(
        daemon, "process_fastapi_deletions", handler
    )

    daemon.process_jobs()

    handler.assert_called_once()
