from unittest.mock import MagicMock, Mock

from worker import daemon, delete_once, monitor, run_once


def make_engine(monkeypatch, module, *, transactional=False):
    connection = MagicMock()
    fake_engine = MagicMock()

    if transactional:
        fake_engine.begin.return_value.__enter__.return_value = (
            connection
        )
    else:
        fake_engine.connect.return_value.__enter__.return_value = (
            connection
        )

    monkeypatch.setattr(module, "engine", fake_engine)

    return connection


def test_claim_job_selects_only_nginx(monkeypatch):
    connection = make_engine(
        monkeypatch,
        run_once,
        transactional=True,
    )

    connection.execute.return_value.mappings.return_value.first.return_value = None

    assert run_once.claim_job() is None

    sql = str(connection.execute.call_args.args[0])

    assert "status = 'pending'" in sql
    assert "template = 'nginx'" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_monitor_selects_only_nginx(monkeypatch):
    connection = make_engine(monkeypatch, monitor)

    database = Mock()
    database.scalar_one.return_value = "devtesthub"

    results = MagicMock()
    results.mappings.return_value.all.return_value = []

    connection.execute.side_effect = [
        database,
        results,
    ]

    assert monitor.get_running_environments() == []

    sql = str(connection.execute.call_args_list[1].args[0])

    assert "status = 'running'" in sql
    assert "template = 'nginx'" in sql


def test_mark_failed_restricts_template(monkeypatch):
    connection = make_engine(
        monkeypatch,
        monitor,
        transactional=True,
    )

    connection.execute.return_value.rowcount = 0

    environment = {
        "id": 15,
        "container_id": "a" * 64,
        "host_port": 52586,
    }

    assert monitor.mark_failed(environment) is False

    sql = str(connection.execute.call_args.args[0])

    assert "template = 'nginx'" in sql
    assert "status = 'running'" in sql


def test_delete_rejects_other_templates(monkeypatch):
    connection = make_engine(
        monkeypatch,
        delete_once,
        transactional=True,
    )

    database = Mock()
    database.scalar_one.return_value = "devtesthub"

    result = MagicMock()
    result.mappings.return_value.first.return_value = None

    connection.execute.side_effect = [
        database,
        result,
    ]

    docker_from_env = Mock(
        side_effect=AssertionError(
            "Docker не должен использоваться"
        )
    )

    monkeypatch.setattr(
        delete_once.docker,
        "from_env",
        docker_from_env,
    )

    delete_once.delete_environment(
        environment_id=15,
        apply=True,
    )

    sql = str(connection.execute.call_args_list[1].args[0])

    assert "template = 'nginx'" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql

    assert connection.execute.call_count == 2
    docker_from_env.assert_not_called()


def test_daemon_routes_only_nginx_jobs(monkeypatch):
    connection = make_engine(monkeypatch, daemon)

    database = Mock()
    database.scalar_one.return_value = "devtesthub"

    deleting = MagicMock()
    deleting.scalars.return_value.all.return_value = []

    pending = Mock()
    pending.scalar_one.return_value = False

    connection.execute.side_effect = [
        database,
        deleting,
        pending,
    ]

    deleting_ids, has_pending = daemon.get_jobs()

    assert deleting_ids == []
    assert has_pending is False

    deleting_sql = str(
        connection.execute.call_args_list[1].args[0]
    )
    pending_sql = str(
        connection.execute.call_args_list[2].args[0]
    )

    assert "template = 'nginx'" in deleting_sql
    assert "template = 'nginx'" in pending_sql
