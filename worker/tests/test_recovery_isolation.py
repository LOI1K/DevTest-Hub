from unittest.mock import MagicMock, Mock

from worker import recover_once


def test_nginx_recovery_ignores_other_templates(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    jobs_result = MagicMock()
    jobs_result.mappings.return_value.all.return_value = []

    connection.execute.side_effect = [
        database_result,
        jobs_result,
    ]

    fake_engine = MagicMock()
    fake_engine.connect.return_value.__enter__.return_value = (
        connection
    )

    monkeypatch.setattr(
        recover_once,
        "engine",
        fake_engine,
    )

    jobs = recover_once.get_unfinished_jobs()

    assert jobs == []

    query = connection.execute.call_args_list[1].args[0]
    sql = str(query)

    assert "status = 'deploying'" in sql
    assert "template = 'nginx'" in sql
    assert "owner_id IS NOT NULL" in sql