from unittest.mock import MagicMock, Mock

import pytest

from worker import run_fastapi_postgres_once as runner


JOB = {
    "id": 15,
    "name": "fastapi-test",
    "template": "fastapi-postgres",
    "owner_id": 3,
}


def test_claim_selects_only_fastapi_postgres(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    job_result = MagicMock()
    job_result.mappings.return_value.first.return_value = JOB

    connection.execute.side_effect = [
        database_result,
        job_result,
    ]

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(runner, "engine", fake_engine)

    result = runner.claim_fastapi_job()

    assert result == JOB

    sql = str(connection.execute.call_args_list[1].args[0])

    assert "template = 'fastapi-postgres'" in sql
    assert "status = 'pending'" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "SET status = 'deploying'" in sql


def test_no_pending_job_skips_docker(monkeypatch):
    monkeypatch.setattr(
        runner,
        "claim_fastapi_job",
        Mock(return_value=None),
    )

    docker_from_env = Mock()

    monkeypatch.setattr(
        runner.docker,
        "from_env",
        docker_from_env,
    )

    assert runner.main() is False

    docker_from_env.assert_not_called()


def test_deployment_success(monkeypatch):
    monkeypatch.setattr(
        runner,
        "claim_fastapi_job",
        Mock(return_value=JOB),
    )

    client = MagicMock()
    client.ping.return_value = True

    monkeypatch.setattr(
        runner.docker,
        "from_env",
        Mock(return_value=client),
    )

    deploy = Mock(return_value=("a" * 64, 52586))

    monkeypatch.setattr(
        runner,
        "deploy_environment",
        deploy,
    )

    assert runner.main() is True

    deploy.assert_called_once_with(client, 15)
    client.close.assert_called_once()


def test_failure_preserves_unfinished_job(monkeypatch):
    monkeypatch.setattr(
        runner,
        "claim_fastapi_job",
        Mock(return_value=JOB),
    )

    client = MagicMock()
    client.ping.return_value = True

    monkeypatch.setattr(
        runner.docker,
        "from_env",
        Mock(return_value=client),
    )

    monkeypatch.setattr(
        runner,
        "deploy_environment",
        Mock(side_effect=RuntimeError("Deployment failed")),
    )

    with pytest.raises(
        RuntimeError,
        match="Deployment failed",
    ):
        runner.main()

    client.close.assert_called_once()