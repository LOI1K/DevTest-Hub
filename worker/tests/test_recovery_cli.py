from unittest.mock import MagicMock, Mock, call

from worker import recover_fastapi_postgres as recovery


ENVIRONMENTS = [
    {"id": 15, "name": "recovery-test"},
]


def prepare_cli(monkeypatch, environments=None):
    if environments is None:
        environments = ENVIRONMENTS

    client = MagicMock()
    client.ping.return_value = True

    monkeypatch.setattr(
        recovery,
        "get_unfinished_environments",
        lambda: environments,
    )

    monkeypatch.setattr(
        recovery.docker,
        "from_env",
        Mock(return_value=client),
    )

    return client


def test_no_jobs_does_not_connect_to_docker(monkeypatch):
    prepare_cli(monkeypatch, environments=[])

    assert recovery.main([]) == 0

    recovery.docker.from_env.assert_not_called()


def test_default_mode_is_read_only(monkeypatch):
    client = prepare_cli(monkeypatch)

    inspect = Mock()
    recover = Mock()

    monkeypatch.setattr(
        recovery,
        "inspect_environment",
        inspect,
    )

    monkeypatch.setattr(
        recovery,
        "recover_ready_environment",
        recover,
    )

    assert recovery.main([]) == 0

    inspect.assert_called_once_with(
        client,
        ENVIRONMENTS[0],
    )

    recover.assert_not_called()
    client.close.assert_called_once()


def test_apply_calls_recovery(monkeypatch):
    client = prepare_cli(monkeypatch)

    recover = Mock(return_value=True)
    inspect = Mock()

    monkeypatch.setattr(
        recovery,
        "recover_ready_environment",
        recover,
    )

    monkeypatch.setattr(
        recovery,
        "inspect_environment",
        inspect,
    )

    assert recovery.main(["--apply"]) == 0

    recover.assert_called_once_with(client, 15)
    inspect.assert_not_called()
    client.close.assert_called_once()


def test_unready_environment_returns_failure(monkeypatch):
    client = prepare_cli(monkeypatch)

    recover = Mock(return_value=False)

    monkeypatch.setattr(
        recovery,
        "recover_ready_environment",
        recover,
    )

    assert recovery.main(["--apply"]) == 1

    recover.assert_called_once_with(client, 15)
    client.close.assert_called_once()


def test_recovery_continues_after_error(monkeypatch):
    client = prepare_cli(
        monkeypatch,
        environments=[
            {"id": 15, "name": "first"},
            {"id": 16, "name": "second"},
        ],
    )

    recover = Mock(
        side_effect=[
            RuntimeError("Recovery failed"),
            True,
        ]
    )

    monkeypatch.setattr(
        recovery,
        "recover_ready_environment",
        recover,
    )

    assert recovery.main(["--apply"]) == 1

    assert recover.call_args_list == [
        call(client, 15),
        call(client, 16),
    ]

    client.close.assert_called_once()
