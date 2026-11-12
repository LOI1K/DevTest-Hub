from unittest.mock import MagicMock

import pytest
from docker.errors import NotFound

from worker.deploy_fastapi_postgres import (
    check_deployment_prerequisites,
    get_resource_labels,
    get_resource_names,
    is_managed_resource,
)

from unittest.mock import Mock


def test_resource_names():
    names = get_resource_names(15)

    assert names == {
        "api": "devtest-hub-env-15-api",
        "postgres": "devtest-hub-env-15-db",
        "network": "devtest-hub-env-15-net",
        "volume": "devtest-hub-env-15-data",
    }


@pytest.mark.parametrize(
    "environment_id",
    [0, -1, True, "15"],
)
def test_invalid_environment_id(environment_id):
    with pytest.raises(ValueError):
        get_resource_names(environment_id)


def test_resource_labels():
    labels = get_resource_labels(15, "postgres")

    assert labels == {
        "devtest-hub.managed": "true",
        "devtest-hub.environment-id": "15",
        "devtest-hub.role": "postgres",
    }


def test_invalid_resource_role():
    with pytest.raises(ValueError):
        get_resource_labels(15, "unknown")


def test_managed_resource():
    resource = MagicMock()

    resource.name = "devtest-hub-env-15-api"
    resource.labels = get_resource_labels(15, "api")

    assert is_managed_resource(
        resource,
        15,
        "api",
        "devtest-hub-env-15-api",
    )


def test_foreign_resource_is_rejected():
    resource = MagicMock()

    resource.name = "devtest-hub-env-15-api"
    resource.labels = get_resource_labels(999, "api")

    assert not is_managed_resource(
        resource,
        15,
        "api",
        "devtest-hub-env-15-api",
    )


def test_prerequisites_success():
    client = MagicMock()

    client.containers.get.side_effect = NotFound("not found")
    client.networks.get.side_effect = NotFound("not found")
    client.volumes.get.side_effect = NotFound("not found")

    names = check_deployment_prerequisites(client, 15)

    assert names["api"] == "devtest-hub-env-15-api"
    assert names["postgres"] == "devtest-hub-env-15-db"

    client.images.get.assert_called_once_with(
        "devtest-hub-fastapi-postgres:dev"
    )


def test_existing_resource_blocks_deployment():
    client = MagicMock()

    with pytest.raises(RuntimeError, match="уже существует"):
        check_deployment_prerequisites(client, 15)


def test_missing_image_blocks_deployment():
    client = MagicMock()
    client.images.get.side_effect = NotFound("not found")

    with pytest.raises(RuntimeError, match="Не найден Docker-образ"):
        check_deployment_prerequisites(client, 15)


def make_client_for_creation():
    client = MagicMock()

    client.containers.get.side_effect = NotFound(
        "not found"
    )
    client.networks.get.side_effect = NotFound(
        "not found"
    )
    client.volumes.get.side_effect = NotFound(
        "not found"
    )

    network = MagicMock()
    network.name = "devtest-hub-env-15-net"
    network.labels = get_resource_labels(
        15,
        "network",
    )

    volume = MagicMock()
    volume.name = "devtest-hub-env-15-data"
    volume.labels = get_resource_labels(
        15,
        "volume",
    )

    client.networks.create.return_value = network
    client.volumes.create.return_value = volume

    return client, network, volume


def test_create_base_resources():
    from worker.deploy_fastapi_postgres import (
        create_base_resources,
    )

    client, network, volume = make_client_for_creation()

    created = create_base_resources(client, 15)

    assert created == [
        ("network", network),
        ("volume", volume),
    ]

    client.networks.create.assert_called_once()
    client.volumes.create.assert_called_once()


def test_volume_failure_removes_network():
    from worker.deploy_fastapi_postgres import (
        create_base_resources,
    )

    client, network, _ = make_client_for_creation()

    client.volumes.create.side_effect = RuntimeError(
        "Volume creation failed"
    )

    with pytest.raises(
        RuntimeError,
        match="Volume creation failed",
    ):
        create_base_resources(client, 15)

    network.remove.assert_called_once()


def test_cleanup_uses_reverse_order():
    from worker.deploy_fastapi_postgres import (
        cleanup_created_resources,
    )

    _, network, volume = make_client_for_creation()

    cleanup_created_resources(
        15,
        [
            ("network", network),
            ("volume", volume),
        ],
    )

    assert volume.remove.call_count == 1
    assert network.remove.call_count == 1


def test_cleanup_rejects_foreign_resource():
    from worker.deploy_fastapi_postgres import (
        cleanup_created_resources,
    )

    _, network, _ = make_client_for_creation()

    network.labels = get_resource_labels(
        999,
        "network",
    )

    with pytest.raises(
        RuntimeError,
        match="Не удалось очистить все ресурсы",
    ):
        cleanup_created_resources(
            15,
            [("network", network)],
        )

    network.remove.assert_not_called()


from worker import deploy_fastapi_postgres as deployment


def make_postgres_test_objects():
    client, network, volume = make_client_for_creation()

    container = MagicMock()
    container.name = "devtest-hub-env-15-db"
    container.labels = get_resource_labels(15, "postgres")
    container.status = "running"
    container.attrs = {
        "State": {
            "Health": {"Status": "healthy"}
        }
    }

    client.containers.create.return_value = container

    created = [
        ("network", network),
        ("volume", volume),
    ]

    return client, container, created


def test_postgres_creation(monkeypatch):
    client, container, created = make_postgres_test_objects()

    monkeypatch.setattr(
        deployment.secrets,
        "token_urlsafe",
        lambda size: "test-password",
    )

    result, password = deployment.create_postgres_container(
        client, 15, created
    )

    assert result is container
    assert password == "test-password"
    assert created[-1] == ("postgres", container)

    kwargs = client.containers.create.call_args.kwargs

    assert kwargs["image"] == "postgres:18"
    assert kwargs["network"] == "devtest-hub-env-15-net"
    assert kwargs["environment"]["POSTGRES_PASSWORD"] == password
    assert kwargs["volumes"]["devtest-hub-env-15-data"]["bind"] == "/var/lib/postgresql"
    assert "ports" not in kwargs

    container.start.assert_called_once()


def test_postgres_exited_is_rejected():
    container = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {}}

    with pytest.raises(RuntimeError, match="аварийно"):
        deployment.wait_for_postgres_ready(container)


def test_postgres_timeout(monkeypatch):
    container = MagicMock()
    container.status = "running"
    container.attrs = {
        "State": {"Health": {"Status": "starting"}}
    }

    clock = iter([0, 100])

    monkeypatch.setattr(
        deployment.time,
        "monotonic",
        lambda: next(clock),
    )

    with pytest.raises(TimeoutError):
        deployment.wait_for_postgres_ready(container, timeout=90)


def test_postgres_start_failure_cleans_up():
    client, container, created = make_postgres_test_objects()

    container.start.side_effect = RuntimeError("Start failed")
    container.status = "created"

    with pytest.raises(RuntimeError, match="Start failed"):
        deployment.create_postgres_container(
            client, 15, created
        )

    container.remove.assert_not_called()

    assert [role for role, _ in created] == [
        "network",
        "volume",
        "postgres",
    ]


def test_postgres_requires_base_resources():
    client = MagicMock()

    with pytest.raises(
        RuntimeError,
        match="Не создан необходимый ресурс",
    ):
        deployment.create_postgres_container(
            client, 15, []
        )

    client.containers.create.assert_not_called()


def make_api_test_objects():
    client, postgres, created = make_postgres_test_objects()

    postgres.attrs = {
        "State": {
            "Health": {"Status": "healthy"}
        }
    }

    created.append(("postgres", postgres))

    api = MagicMock()
    api.name = "devtest-hub-env-15-api"
    api.labels = get_resource_labels(15, "api")
    api.status = "running"
    api.attrs = {
        "State": {
            "Health": {"Status": "healthy"}
        },
        "NetworkSettings": {
            "Ports": {
                "8000/tcp": [{
                    "HostIp": "127.0.0.1",
                    "HostPort": "52586",
                }]
            }
        },
    }

    client.containers.create.return_value = api

    return client, postgres, api, created


def test_api_creation():
    client, postgres, api, created = make_api_test_objects()

    result, port = deployment.create_api_container(
        client, 15, created, "test-password"
    )

    assert result is api
    assert port == 52586
    assert created[-1] == ("api", api)

    kwargs = client.containers.create.call_args.kwargs

    assert kwargs["image"] == deployment.FASTAPI_IMAGE
    assert kwargs["network"] == "devtest-hub-env-15-net"
    assert kwargs["environment"]["DB_HOST"] == "devtest-hub-env-15-db"
    assert kwargs["environment"]["DB_PASSWORD"] == "test-password"
    assert kwargs["ports"]["8000/tcp"] == ("127.0.0.1", None)

    api.start.assert_called_once()


def test_api_requires_postgres():
    client = MagicMock()

    with pytest.raises(
        RuntimeError,
        match="Не создан необходимый ресурс",
    ):
        deployment.create_api_container(
            client, 15, [], "test-password"
        )

    client.containers.create.assert_not_called()


def test_api_rejects_foreign_postgres():
    client, postgres, api, created = make_api_test_objects()

    postgres.labels = get_resource_labels(999, "postgres")

    with pytest.raises(
        RuntimeError,
        match="не прошёл проверку принадлежности",
    ):
        deployment.create_api_container(
            client, 15, created, "test-password"
        )

    client.containers.create.assert_not_called()


def test_api_start_failure_cleans_resources():
    client, postgres, api, created = make_api_test_objects()

    api.start.side_effect = RuntimeError("API start failed")
    api.status = "created"

    with pytest.raises(RuntimeError, match="API start failed"):
        deployment.create_api_container(
            client, 15, created, "test-password"
        )

    api.remove.assert_not_called()
    postgres.stop.assert_not_called()
    postgres.remove.assert_not_called()

    assert [role for role, _ in created] == [
        "network",
        "volume",
        "postgres",
        "api",
    ]


def test_api_rejects_public_binding():
    client, postgres, api, created = make_api_test_objects()

    api.attrs["NetworkSettings"]["Ports"]["8000/tcp"][0][
        "HostIp"
    ] = "0.0.0.0"

    with pytest.raises(
        RuntimeError,
        match="не прошёл проверку безопасности",
    ):
        deployment.create_api_container(
            client, 15, created, "test-password"
        )

    api.remove.assert_not_called()

    assert [role for role, _ in created] == [
        "network",
        "volume",
        "postgres",
        "api",
    ]


def test_api_exited_is_rejected():
    container = MagicMock()
    container.status = "exited"
    container.attrs = {"State": {}}

    with pytest.raises(RuntimeError, match="аварийно"):
        deployment.wait_for_api_ready(container)


def test_api_timeout(monkeypatch):
    container = MagicMock()
    container.status = "running"
    container.attrs = {
        "State": {
            "Health": {"Status": "starting"}
        }
    }

    clock = iter([0, 121])

    monkeypatch.setattr(
        deployment.time,
        "monotonic",
        lambda: next(clock),
    )

    with pytest.raises(TimeoutError):
        deployment.wait_for_api_ready(
            container,
            timeout=120,
        )


def test_api_unhealthy_is_rejected():
    container = MagicMock()
    container.status = "running"
    container.attrs = {
        "State": {
            "Health": {"Status": "unhealthy"}
        }
    }

    with pytest.raises(
        RuntimeError,
        match="не прошла проверку готовности",
    ):
        deployment.wait_for_api_ready(container)


def make_orchestration_objects():
    client = MagicMock()

    network = MagicMock()
    network.name = "devtest-hub-env-15-net"
    network.labels = get_resource_labels(15, "network")

    volume = MagicMock()
    volume.name = "devtest-hub-env-15-data"
    volume.labels = get_resource_labels(15, "volume")

    postgres = MagicMock()
    postgres.name = "devtest-hub-env-15-db"
    postgres.id = "b" * 64
    postgres.labels = get_resource_labels(15, "postgres")

    api = MagicMock()
    api.name = "devtest-hub-env-15-api"
    api.id = "a" * 64
    api.labels = get_resource_labels(15, "api")

    return client, network, volume, postgres, api


def test_deploy_environment_success(monkeypatch):
    client, network, volume, postgres, api = (
        make_orchestration_objects()
    )

    def fake_base(client, environment_id, created):
      created.extend([
          ("network", network),
          ("volume", volume),
      ])
      return created

    def fake_postgres(client, environment_id, created):
        created.append(("postgres", postgres))
        return postgres, "test-password"

    def fake_api(
        client,
        environment_id,
        created,
        db_password,
    ):
        assert db_password == "test-password"
        created.append(("api", api))
        return api, 52586

    register = Mock(return_value=1)
    finalize = Mock()

    monkeypatch.setattr(
        deployment, "create_base_resources", fake_base
    )
    monkeypatch.setattr(
        deployment, "create_postgres_container", fake_postgres
    )
    monkeypatch.setattr(
        deployment, "create_api_container", fake_api
    )
    monkeypatch.setattr(
        deployment, "register_resource", register
    )
    monkeypatch.setattr(
        deployment, "finalize_deployment", finalize
    )

    result = deployment.deploy_environment(client, 15)

    assert result == ("a" * 64, 52586)
    assert register.call_count == 4

    finalize.assert_called_once_with(
        15, "a" * 64, 52586
    )


def test_deployment_registry_failure_cleans_resources(
    monkeypatch,
):
    client, network, volume, _, _ = (
        make_orchestration_objects()
    )

    monkeypatch.setattr(
        deployment,
        "create_base_resources",
        lambda client, environment_id, created: created.extend([
          ("network", network),
          ("volume", volume),
      ]),
    )

    monkeypatch.setattr(
        deployment,
        "register_resource",
        Mock(side_effect=RuntimeError("Registry failed")),
    )

    def fake_cleanup(environment_id, created):
        created.clear()

    cleanup = Mock(side_effect=fake_cleanup)
    clear_records = Mock()

    monkeypatch.setattr(
        deployment, "cleanup_created_resources", cleanup
    )
    monkeypatch.setattr(
        deployment, "clear_deployment_records", clear_records
    )

    with pytest.raises(RuntimeError, match="Registry failed"):
        deployment.deploy_environment(client, 15)

    cleanup.assert_called_once()
    clear_records.assert_called_once_with(15)


def test_failed_cleanup_preserves_registry(monkeypatch):
    client, network, volume, _, _ = (
        make_orchestration_objects()
    )

    monkeypatch.setattr(
        deployment,
        "create_base_resources",
        lambda client, environment_id, created: created.extend([
            ("network", network),
            ("volume", volume),
        ]),
    )

    monkeypatch.setattr(
        deployment,
        "register_resource",
        Mock(side_effect=RuntimeError("Registry failed")),
    )

    monkeypatch.setattr(
        deployment,
        "cleanup_created_resources",
        Mock(side_effect=RuntimeError("Cleanup failed")),
    )

    clear_records = Mock()

    monkeypatch.setattr(
        deployment, "clear_deployment_records", clear_records
    )

    with pytest.raises(RuntimeError, match="Registry failed"):
        deployment.deploy_environment(client, 15)

    clear_records.assert_not_called()


def test_register_created_resource_rejects_foreign_resource(
    monkeypatch,
):
    resource = MagicMock()
    resource.name = "devtest-hub-env-15-api"
    resource.id = "a" * 64
    resource.labels = get_resource_labels(999, "api")

    register = Mock()

    monkeypatch.setattr(
        deployment, "register_resource", register
    )

    with pytest.raises(
        RuntimeError,
        match="не прошёл проверку принадлежности",
    ):
        deployment.register_created_resource(
            15, "api", resource
        )

    register.assert_not_called()


def test_finalize_deployment_is_conditional(monkeypatch):
    connection = MagicMock()

    database_result = Mock()
    database_result.scalar_one.return_value = "devtesthub"

    update_result = Mock()
    update_result.rowcount = 1

    connection.execute.side_effect = [
        database_result,
        update_result,
    ]

    fake_engine = MagicMock()
    fake_engine.begin.return_value.__enter__.return_value = connection

    monkeypatch.setattr(
        deployment, "engine", fake_engine
    )

    deployment.finalize_deployment(
        15, "a" * 64, 52586
    )

    query, parameters = connection.execute.call_args_list[1].args

    sql = str(query)

    assert "e.status = 'deploying'" in sql
    assert "e.template = 'fastapi-postgres'" in sql
    assert "COUNT(*)" in sql

    assert parameters["environment_id"] == 15
    assert parameters["host_port"] == 52586


def test_rollback_preserves_postgres_and_volume():
    _, postgres, created = make_postgres_test_objects()

    created.append(("postgres", postgres))

    with pytest.raises(
        RuntimeError,
        match="Автоматический откат запрещён",
    ):
        deployment.cleanup_created_resources(
            15,
            created,
        )

    assert len(created) == 3

    for _, resource in created:
        resource.remove.assert_not_called()


def test_cleanup_handles_already_missing_resource():
    _, network, volume = make_client_for_creation()

    network.reload.side_effect = NotFound("Already removed")

    created = [
        ("network", network),
        ("volume", volume),
    ]

    deployment.cleanup_created_resources(
        15,
        created,
    )

    assert created == []
    volume.remove.assert_called_once()
    network.remove.assert_not_called()


def test_base_resource_failure_preserves_tracking():
    client, network, _ = make_client_for_creation()

    client.volumes.create.side_effect = RuntimeError(
        "Volume creation failed"
    )

    network.remove.side_effect = RuntimeError(
        "Network is busy"
    )

    created = []

    with pytest.raises(
        RuntimeError,
        match="Volume creation failed",
    ):
        deployment.create_base_resources(
            client,
            15,
            created,
        )

    assert created == [("network", network)]


def test_failed_preflight_preserves_registry(monkeypatch):
    client = MagicMock()

    monkeypatch.setattr(
        deployment,
        "create_base_resources",
        Mock(side_effect=RuntimeError("Resource conflict")),
    )

    clear_records = Mock()

    monkeypatch.setattr(
        deployment,
        "clear_deployment_records",
        clear_records,
    )

    with pytest.raises(
        RuntimeError,
        match="Resource conflict",
    ):
        deployment.deploy_environment(client, 15)

    clear_records.assert_not_called()


def test_postgres_failure_preserves_all_resources(monkeypatch):
    client, network, volume = make_client_for_creation()

    postgres = MagicMock()
    postgres.name = "devtest-hub-env-15-db"
    postgres.labels = get_resource_labels(15, "postgres")

    def fake_base(client, environment_id, created):
        created.extend([
            ("network", network),
            ("volume", volume),
        ])

    def fake_postgres(client, environment_id, created):
        created.append(("postgres", postgres))
        raise RuntimeError("Postgres startup failed")

    monkeypatch.setattr(
        deployment,
        "create_base_resources",
        fake_base,
    )

    monkeypatch.setattr(
        deployment,
        "create_postgres_container",
        fake_postgres,
    )

    monkeypatch.setattr(
        deployment,
        "register_resource",
        Mock(return_value=1),
    )

    clear_records = Mock()

    monkeypatch.setattr(
        deployment,
        "clear_deployment_records",
        clear_records,
    )

    with pytest.raises(
        RuntimeError,
        match="Postgres startup failed",
    ):
        deployment.deploy_environment(client, 15)

    postgres.remove.assert_not_called()
    network.remove.assert_not_called()
    volume.remove.assert_not_called()

    clear_records.assert_not_called()
