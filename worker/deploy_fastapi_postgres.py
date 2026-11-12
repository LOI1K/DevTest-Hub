import secrets
import time
import re

from sqlalchemy import text

from worker.database import engine
from worker.resource_registry import (
    clear_deployment_records,
    register_resource,
)


from docker.errors import NotFound


FASTAPI_IMAGE = "devtest-hub-fastapi-postgres:dev"

RESOURCE_ROLES = {
    "api",
    "postgres",
    "network",
    "volume",
}


def get_resource_names(environment_id: int) -> dict[str, str]:
    if type(environment_id) is not int or environment_id <= 0:
        raise ValueError("Некорректный ID тестовой среды")

    prefix = f"devtest-hub-env-{environment_id}"

    return {
        "api": f"{prefix}-api",
        "postgres": f"{prefix}-db",
        "network": f"{prefix}-net",
        "volume": f"{prefix}-data",
    }


def get_resource_labels(
    environment_id: int,
    role: str,
) -> dict[str, str]:
    get_resource_names(environment_id)

    if role not in RESOURCE_ROLES:
        raise ValueError("Неизвестная роль Docker-ресурса")

    return {
        "devtest-hub.managed": "true",
        "devtest-hub.environment-id": str(environment_id),
        "devtest-hub.role": role,
    }


def is_managed_resource(
    resource,
    environment_id: int,
    role: str,
    expected_name: str,
) -> bool:
    labels = getattr(resource, "labels", None)

    if labels is None:
        labels = (resource.attrs or {}).get("Labels", {})

    return (
        resource.name == expected_name
        and labels.get("devtest-hub.managed") == "true"
        and labels.get("devtest-hub.environment-id")
        == str(environment_id)
        and labels.get("devtest-hub.role") == role
    )


def check_deployment_prerequisites(
    client,
    environment_id: int,
) -> dict[str, str]:
    names = get_resource_names(environment_id)

    try:
        client.images.get(FASTAPI_IMAGE)
    except NotFound as error:
        raise RuntimeError(
            f"Не найден Docker-образ {FASTAPI_IMAGE}"
        ) from error

    lookups = {
        "api": client.containers.get,
        "postgres": client.containers.get,
        "network": client.networks.get,
        "volume": client.volumes.get,
    }

    for role, name in names.items():
        try:
            lookups[role](name)
        except NotFound:
            continue

        raise RuntimeError(
            f"Docker-ресурс уже существует: {name}. "
            "Требуется проверка перед развёртыванием."
        )

    return names


def cleanup_created_resources(
    environment_id: int,
    created: list[tuple[str, object]],
) -> None:
    names = get_resource_names(environment_id)

    # После создания контейнера автоматическое удаление
    # запрещено: PostgreSQL уже могла записать данные.
    if any(
        role not in {"network", "volume"}
        for role, _ in created
    ):
        raise RuntimeError(
            "Автоматический откат запрещён: "
            "уже создан контейнер. "
            "Docker-ресурсы сохранены для восстановления."
        )

    errors = []
    remaining = []

    for role, resource in reversed(created):
        try:
            resource.reload()

            if not is_managed_resource(
                resource,
                environment_id,
                role,
                names[role],
            ):
                raise RuntimeError(
                    f"Ресурс {names[role]} "
                    "не прошёл проверку принадлежности"
                )

            resource.remove()
            print(f"Ресурс удалён: {names[role]}")

        except NotFound:
            # Ресурс уже отсутствует.
            # Повторное удаление не требуется.
            print(f"Ресурс уже отсутствует: {names[role]}")

        except Exception as error:
            errors.append(f"{names[role]}: {error}")
            remaining.append((role, resource))

    # Сохраняем список ресурсов, которые не удалось удалить.
    created[:] = list(reversed(remaining))

    if errors:
        raise RuntimeError(
            "Не удалось очистить все ресурсы: "
            + "; ".join(errors)
        )


def create_base_resources(
    client,
    environment_id: int,
    created: list[tuple[str, object]] | None = None,
) -> list[tuple[str, object]]:
    if created is None:
        created = []
    elif created:
        raise ValueError(
            "Список создаваемых ресурсов должен быть пуст"
        )

    names = check_deployment_prerequisites(
        client,
        environment_id,
    )

    try:
        network = client.networks.create(
            name=names["network"],
            driver="bridge",
            check_duplicate=True,
            labels=get_resource_labels(
                environment_id,
                "network",
            ),
        )

        created.append(("network", network))
        print(f"Создана Docker-сеть: {network.name}")

        volume = client.volumes.create(
            name=names["volume"],
            driver="local",
            labels=get_resource_labels(
                environment_id,
                "volume",
            ),
        )

        created.append(("volume", volume))
        print(f"Создан Docker Volume: {volume.name}")

        return created

    except Exception:
        try:
            cleanup_created_resources(
                environment_id,
                created,
            )
        except Exception as cleanup_error:
            print(
                "Не удалось полностью откатить "
                "создание инфраструктуры:",
                cleanup_error,
            )

        raise


def wait_for_postgres_ready(container, timeout=90):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        container.reload()

        if container.status in {"exited", "dead"}:
            raise RuntimeError(
                "PostgreSQL-контейнер аварийно завершился"
            )

        health = (
            container.attrs.get("State", {})
            .get("Health", {})
            .get("Status")
        )

        if container.status == "running" and health == "healthy":
            return

        if health == "unhealthy":
            raise RuntimeError(
                "PostgreSQL не прошла проверку готовности"
            )

        time.sleep(2)

    raise TimeoutError(
        "Превышено время ожидания готовности PostgreSQL"
    )


def create_postgres_container(
    client,
    environment_id: int,
    created: list[tuple[str, object]],
):
    names = get_resource_names(environment_id)

    resources = dict(created)

    if "postgres" in resources:
        raise RuntimeError(
            "PostgreSQL уже добавлена в список ресурсов"
        )

    for role in ("network", "volume"):
        resource = resources.get(role)

        if resource is None:
            raise RuntimeError(
                f"Не создан необходимый ресурс: {role}"
            )

        resource.reload()

        if not is_managed_resource(
            resource,
            environment_id,
            role,
            names[role],
        ):
            raise RuntimeError(
                f"Ресурс {role} не прошёл проверку принадлежности"
            )

    password = secrets.token_urlsafe(32)

    container = client.containers.create(
        image="postgres:18",
        name=names["postgres"],
        network=names["network"],
        environment={
            "POSTGRES_USER": "appuser",
            "POSTGRES_DB": "appdb",
            "POSTGRES_PASSWORD": password,
        },
        volumes={
            names["volume"]: {
                "bind": "/var/lib/postgresql",
                "mode": "rw",
            }
        },
        healthcheck={
            "test": [
                "CMD-SHELL",
                "pg_isready -U appuser -d appdb",
            ],
            "interval": 5_000_000_000,
            "timeout": 3_000_000_000,
            "start_period": 15_000_000_000,
            "retries": 15,
        },
        mem_limit="512m",
        nano_cpus=500_000_000,
        pids_limit=128,
        security_opt=["no-new-privileges:true"],
        labels=get_resource_labels(
            environment_id,
            "postgres",
        ),
    )

    created.append(("postgres", container))

    try:
        container.start()
        wait_for_postgres_ready(container)

    except Exception:
        try:
            cleanup_created_resources(
                environment_id,
                created,
            )
        except Exception as cleanup_error:
            print("Ошибка очистки:", cleanup_error)
        else:
            created.clear()

        raise

    print(f"PostgreSQL готова: {container.name}")

    return container, password


def wait_for_api_ready(container, timeout=120):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        container.reload()

        if container.status in {"exited", "dead"}:
            raise RuntimeError(
                "FastAPI-контейнер аварийно завершился"
            )

        health = (
            container.attrs.get("State", {})
            .get("Health", {})
            .get("Status")
        )

        if container.status == "running" and health == "healthy":
            return

        if health == "unhealthy":
            raise RuntimeError(
                "FastAPI не прошла проверку готовности"
            )

        time.sleep(2)

    raise TimeoutError(
        "Превышено время ожидания готовности FastAPI"
    )


def create_api_container(
    client,
    environment_id: int,
    created: list[tuple[str, object]],
    db_password: str,
):
    names = get_resource_names(environment_id)

    if not isinstance(db_password, str) or not db_password:
        raise ValueError("Не указан пароль PostgreSQL")

    resources = dict(created)

    if "api" in resources:
        raise RuntimeError(
            "FastAPI уже добавлена в список ресурсов"
        )

    for role in ("network", "volume", "postgres"):
        resource = resources.get(role)

        if resource is None:
            raise RuntimeError(
                f"Не создан необходимый ресурс: {role}"
            )

        resource.reload()

        if not is_managed_resource(
            resource,
            environment_id,
            role,
            names[role],
        ):
            raise RuntimeError(
                f"Ресурс {role} не прошёл проверку принадлежности"
            )

    postgres = resources["postgres"]

    postgres_health = (
        postgres.attrs.get("State", {})
        .get("Health", {})
        .get("Status")
    )

    if (
        postgres.status != "running"
        or postgres_health != "healthy"
    ):
        raise RuntimeError(
            "PostgreSQL не готова к подключению FastAPI"
        )

    try:
        container = client.containers.create(
            image=FASTAPI_IMAGE,
            name=names["api"],
            network=names["network"],
            ports={
                "8000/tcp": ("127.0.0.1", None),
            },
            environment={
                "DB_HOST": names["postgres"],
                "DB_PORT": "5432",
                "DB_NAME": "appdb",
                "DB_USER": "appuser",
                "DB_PASSWORD": db_password,
            },
            mem_limit="256m",
            nano_cpus=500_000_000,
            pids_limit=64,
            security_opt=[
                "no-new-privileges:true",
            ],
            labels=get_resource_labels(
                environment_id,
                "api",
            ),
        )

        created.append(("api", container))

        container.start()
        wait_for_api_ready(container)

        container.reload()

        bindings = (
            container.attrs.get("NetworkSettings", {})
            .get("Ports") or {}
        ).get("8000/tcp") or []

        if len(bindings) != 1:
            raise RuntimeError(
                "Некорректная конфигурация порта FastAPI"
            )

        binding = bindings[0]

        host_ip = binding.get("HostIp")
        host_port = str(binding.get("HostPort", ""))

        if (
            host_ip != "127.0.0.1"
            or not host_port.isascii()
            or not host_port.isdigit()
            or not 1 <= int(host_port) <= 65535
        ):
            raise RuntimeError(
                "Порт FastAPI не прошёл проверку безопасности"
            )

        print(f"FastAPI готова: {container.name}")
        print(f"Адрес: http://127.0.0.1:{host_port}")

        return container, int(host_port)

    except Exception:
        try:
            cleanup_created_resources(
                environment_id,
                created,
            )
        except Exception as cleanup_error:
            print("Ошибка очистки:", cleanup_error)
        else:
            created.clear()

        raise


def register_created_resource(
    environment_id: int,
    role: str,
    resource,
) -> int:
    names = get_resource_names(environment_id)

    resource_types = {
        "network": "network",
        "volume": "volume",
        "postgres": "container",
        "api": "container",
    }

    if role not in resource_types:
        raise ValueError("Неизвестная роль ресурса")

    resource.reload()

    if not is_managed_resource(
        resource,
        environment_id,
        role,
        names[role],
    ):
        raise RuntimeError(
            f"Ресурс {names[role]} не прошёл проверку принадлежности"
        )

    docker_id = None

    if role in {"postgres", "api"}:
        docker_id = resource.id

    return register_resource(
        environment_id=environment_id,
        resource_type=resource_types[role],
        role=role,
        resource_name=names[role],
        docker_id=docker_id,
    )


def finalize_deployment(
    environment_id: int,
    api_container_id: str,
    host_port: int,
) -> None:
    get_resource_names(environment_id)

    if not isinstance(api_container_id, str) or not re.fullmatch(
        r"[0-9a-f]{64}",
        api_container_id,
    ):
        raise ValueError("Некорректный Docker ID FastAPI")

    if type(host_port) is not int or not 1 <= host_port <= 65535:
        raise ValueError("Некорректный порт FastAPI")

    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        result = connection.execute(
            text("""
                UPDATE environments AS e
                SET status = 'running',
                    container_id = :api_container_id,
                    host_port = :host_port
                WHERE e.id = :environment_id
                  AND e.template = 'fastapi-postgres'
                  AND e.status = 'deploying'
                  AND e.container_id IS NULL
                  AND e.host_port IS NULL
                  AND (
                      SELECT COUNT(*)
                      FROM environment_resources AS r
                      WHERE r.environment_id = e.id
                  ) = 4
            """),
            {
                "environment_id": environment_id,
                "api_container_id": api_container_id,
                "host_port": host_port,
            },
        )

        if result.rowcount != 1:
            raise RuntimeError(
                "Не удалось завершить развёртывание. "
                "Проверьте состояние среды и регистрацию ресурсов."
            )


def deploy_environment(
    client,
    environment_id: int,
) -> tuple[str, int]:
    get_resource_names(environment_id)

    created = []

    try:
        # 1. Сеть и том.
        create_base_resources(
            client,
            environment_id,
            created,
        )

        for role, resource in created:
            register_created_resource(
                environment_id,
                role,
                resource,
            )

        # 2. PostgreSQL.
        postgres, db_password = create_postgres_container(
            client,
            environment_id,
            created,
        )

        register_created_resource(
            environment_id,
            "postgres",
            postgres,
        )

        # 3. FastAPI.
        api, host_port = create_api_container(
            client,
            environment_id,
            created,
            db_password,
        )

        register_created_resource(
            environment_id,
            "api",
            api,
        )

        # 4. Завершение развёртывания.
        finalize_deployment(
            environment_id,
            api.id,
            host_port,
        )

        print(
            f"Среда №{environment_id} успешно развёрнута."
        )

        return api.id, host_port


    except Exception:
        cleanup_successful = False

        if created:
            try:
                cleanup_created_resources(
                    environment_id,
                    created,
                )
            except Exception as cleanup_error:
                print(
                    "Не удалось полностью очистить Docker:",
                    cleanup_error,
                )
            else:
                # Подтверждаем, что после очистки
                # не осталось отслеживаемых ресурсов.
                cleanup_successful = not created

        if cleanup_successful:
            try:
                clear_deployment_records(environment_id)
            except Exception as registry_error:
                print(
                    "Не удалось очистить реестр ресурсов:",
                    registry_error,
                )
        else:
            print(
                "Записи о ресурсах сохранены "
                "для дальнейшей диагностики."
            )

        raise
