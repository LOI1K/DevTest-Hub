import pytest

from unittest.mock import Mock

from worker import daemon


@pytest.fixture(autouse=True)
def no_fastapi_deletion_jobs(monkeypatch):
    monkeypatch.setattr(
        daemon,
        "get_fastapi_deleting_ids",
        lambda: [],
    )

def prepare_daemon(monkeypatch, *, enabled, pending):
    monkeypatch.setattr(
        daemon,
        "get_jobs",
        Mock(return_value=([], False)),
    )

    monkeypatch.setattr(
        daemon,
        "fastapi_enabled",
        Mock(return_value=enabled),
    )

    has_pending = Mock(return_value=pending)
    run_fastapi = Mock()

    monkeypatch.setattr(
        daemon,
        "has_fastapi_pending",
        has_pending,
    )

    monkeypatch.setattr(
        daemon,
        "run_fastapi_deployment",
        run_fastapi,
    )

    return has_pending, run_fastapi


def test_feature_flag_disabled_by_default(monkeypatch):
    monkeypatch.delenv(
        "DEVTEST_HUB_ENABLE_FASTAPI_POSTGRES",
        raising=False,
    )

    assert daemon.fastapi_enabled() is False

    monkeypatch.setenv(
        "DEVTEST_HUB_ENABLE_FASTAPI_POSTGRES",
        "1",
    )

    assert daemon.fastapi_enabled() is True

    monkeypatch.setenv(
        "DEVTEST_HUB_ENABLE_FASTAPI_POSTGRES",
        "true",
    )

    assert daemon.fastapi_enabled() is False


def test_disabled_template_is_not_processed(monkeypatch):
    has_pending, run_fastapi = prepare_daemon(
        monkeypatch,
        enabled=False,
        pending=True,
    )

    daemon.process_jobs()

    has_pending.assert_not_called()
    run_fastapi.assert_not_called()


def test_enabled_template_is_processed(monkeypatch):
    has_pending, run_fastapi = prepare_daemon(
        monkeypatch,
        enabled=True,
        pending=True,
    )

    daemon.process_jobs()

    has_pending.assert_called_once()
    run_fastapi.assert_called_once()


def test_no_pending_fastapi_job(monkeypatch):
    has_pending, run_fastapi = prepare_daemon(
        monkeypatch,
        enabled=True,
        pending=False,
    )

    daemon.process_jobs()

    has_pending.assert_called_once()
    run_fastapi.assert_not_called()


def test_fastapi_error_does_not_crash_job_loop(monkeypatch):
    has_pending, run_fastapi = prepare_daemon(
        monkeypatch,
        enabled=True,
        pending=True,
    )

    run_fastapi.side_effect = RuntimeError(
        "Deployment failed"
    )

    daemon.process_jobs()

    has_pending.assert_called_once()
    run_fastapi.assert_called_once()
