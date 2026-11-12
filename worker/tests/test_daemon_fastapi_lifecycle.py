from unittest.mock import Mock

from worker import daemon


def prepare_lifecycle(monkeypatch, enabled):
    nginx_recovery = Mock()
    fastapi_recovery = Mock(return_value=0)

    nginx_monitor = Mock()
    fastapi_monitor = Mock(return_value=0)

    monkeypatch.setattr(
        daemon,
        "fastapi_enabled",
        lambda: enabled,
    )
    monkeypatch.setattr(
        daemon,
        "recover_jobs",
        nginx_recovery,
    )
    monkeypatch.setattr(
        daemon,
        "recover_fastapi_environments",
        fastapi_recovery,
    )
    monkeypatch.setattr(
        daemon,
        "monitor_environments",
        nginx_monitor,
    )
    monkeypatch.setattr(
        daemon,
        "monitor_fastapi_environments",
        fastapi_monitor,
    )

    return {
        "nginx_recovery": nginx_recovery,
        "fastapi_recovery": fastapi_recovery,
        "nginx_monitor": nginx_monitor,
        "fastapi_monitor": fastapi_monitor,
    }


def test_disabled_template_skips_fastapi_recovery(monkeypatch):
    mocks = prepare_lifecycle(monkeypatch, enabled=False)

    daemon.run_startup_recovery()

    mocks["nginx_recovery"].assert_called_once_with(apply=True)
    mocks["fastapi_recovery"].assert_not_called()


def test_enabled_template_runs_both_recoveries(monkeypatch):
    mocks = prepare_lifecycle(monkeypatch, enabled=True)

    daemon.run_startup_recovery()

    mocks["nginx_recovery"].assert_called_once_with(apply=True)
    mocks["fastapi_recovery"].assert_called_once_with(
        ["--apply"]
    )


def test_incomplete_fastapi_recovery_does_not_stop_worker(
    monkeypatch,
):
    mocks = prepare_lifecycle(monkeypatch, enabled=True)

    mocks["fastapi_recovery"].return_value = 1

    daemon.run_startup_recovery()

    mocks["nginx_recovery"].assert_called_once()
    mocks["fastapi_recovery"].assert_called_once()


def test_disabled_template_skips_fastapi_monitor(monkeypatch):
    mocks = prepare_lifecycle(monkeypatch, enabled=False)

    daemon.run_periodic_monitoring()

    mocks["nginx_monitor"].assert_called_once_with(
        apply=True
    )
    mocks["fastapi_monitor"].assert_not_called()


def test_enabled_template_runs_both_monitors(monkeypatch):
    mocks = prepare_lifecycle(monkeypatch, enabled=True)

    daemon.run_periodic_monitoring()

    mocks["nginx_monitor"].assert_called_once_with(
        apply=True
    )
    mocks["fastapi_monitor"].assert_called_once_with(
        apply=True
    )


def test_fastapi_monitor_error_does_not_crash_loop(
    monkeypatch,
):
    mocks = prepare_lifecycle(monkeypatch, enabled=True)

    mocks["fastapi_monitor"].side_effect = RuntimeError(
        "Docker unavailable"
    )

    daemon.run_periodic_monitoring()

    mocks["nginx_monitor"].assert_called_once()
    mocks["fastapi_monitor"].assert_called_once()
