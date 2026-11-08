import sys
from unittest.mock import MagicMock, Mock

import pytest

from worker import daemon


@pytest.fixture
def mocked_daemon(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.scalar_one.return_value = True

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = connection

    recover = Mock()
    process = Mock()

    monkeypatch.setattr(daemon, "engine", fake_engine)
    monkeypatch.setattr(daemon, "recover_jobs", recover)
    monkeypatch.setattr(daemon, "process_jobs", process)
    monkeypatch.setattr(sys, "argv", ["worker.daemon", "--once"])

    return connection, recover, process


def test_worker_acquires_and_releases_lock(mocked_daemon):
    connection, recover, process = mocked_daemon

    daemon.main()

    recover.assert_called_once_with(apply=True)
    process.assert_called_once()

    assert connection.execute.call_count == 2

    queries = [
        str(call.args[0])
        for call in connection.execute.call_args_list
    ]

    assert "pg_try_advisory_lock" in queries[0]
    assert "pg_advisory_unlock" in queries[1]


def test_second_worker_does_not_start(mocked_daemon):
    connection, recover, process = mocked_daemon

    connection.execute.return_value.scalar_one.return_value = False

    daemon.main()

    recover.assert_not_called()
    process.assert_not_called()

    assert connection.execute.call_count == 1


def test_lock_released_after_recovery_error(mocked_daemon):
    connection, recover, process = mocked_daemon

    recover.side_effect = RuntimeError("Ошибка восстановления")

    with pytest.raises(RuntimeError, match="Ошибка восстановления"):
        daemon.main()

    process.assert_not_called()

    assert connection.execute.call_count == 2

    unlock_query = str(connection.execute.call_args_list[1].args[0])
    assert "pg_advisory_unlock" in unlock_query


def test_sigterm_stops_worker_and_releases_lock(
    mocked_daemon,
    monkeypatch,
    ):
    connection, recover, process = mocked_daemon

    monkeypatch.setattr(
        sys,
        "argv",
        ["worker.daemon", "--interval", "5"],
    )

    handlers = {}

    def fake_signal(signum, handler):
        if callable(handler):
            handlers[signum] = handler

        return daemon.signal.SIG_DFL

    monkeypatch.setattr(
        daemon.signal,
        "signal",
        fake_signal,
    )

    def stop_worker():
        handlers[daemon.signal.SIGTERM](
            daemon.signal.SIGTERM,
            None,
        )

    process.side_effect = stop_worker

    daemon.main()

    recover.assert_called_once_with(apply=True)
    process.assert_called_once()

    queries = [
        str(call.args[0])
        for call in connection.execute.call_args_list
    ]

    assert "pg_try_advisory_lock" in queries[0]
    assert "pg_advisory_unlock" in queries[-1]