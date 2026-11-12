import docker
import re
import argparse
from docker.errors import NotFound
from sqlalchemy import text

from worker.database import engine
from worker.deploy_fastapi_postgres import (
    get_resource_names,
    is_managed_resource,
)
from worker.resource_registry import get_environment_resources


def get_unfinished_environments():
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        environments = connection.execute(
            text("""
                SELECT id, name
                FROM environments
                WHERE status = 'deploying'
                  AND template = 'fastapi-postgres'
                  AND owner_id IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

    return [dict(item) for item in environments]


def inspect_environment(client, environment):
    environment_id = environment["id"]
    names = get_resource_names(environment_id)

    records = get_environment_resources(environment_id)

    registered = {
        (record["resource_type"], record["role"]): record
        for record in records
    }

    resources = (
        ("network", "network", client.networks.get),
        ("volume", "volume", client.volumes.get),
        ("container", "postgres", client.containers.get),
        ("container", "api", client.containers.get),
    )

    print(
        f"\nСреда №{environment_id}: "
        f"{environment['name']}"
    )

    print(
        f"Записей в environment_resources: {len(records)}"
    )

    for resource_type, role, getter in resources:
        name = names[role]
        record = registered.get((resource_type, role))

        try:
            resource = getter(name)
            resource.reload()

        except NotFound:
            print(f"{role}: Docker-ресурс отсутствует")

            if record is not None:
                print(
                    f"{role}: запись в PostgreSQL существует"
                )

            continue

        if not is_managed_resource(
            resource,
            environment_id,
            role,
            name,
        ):
            print(
                f"{role}: НЕСООТВЕТСТВИЕ принадлежности"
            )
            continue

        if record is None:
            print(
                f"{role}: Docker-ресурс существует, "
                "но не зарегистрирован"
            )
            continue

        if record["resource_name"] != name:
            print(
                f"{role}: НЕСООТВЕТСТВИЕ имени в PostgreSQL"
            )
            continue

        if (
            resource_type == "container"
            and record["docker_id"] != resource.id
        ):
            print(
                f"{role}: НЕСООТВЕТСТВИЕ Docker ID"
            )
            continue

        print(f"{role}: ресурс найден и зарегистрирован")

        if resource_type == "container":
            status = resource.status

            health = (
                resource.attrs.get("State", {})
                .get("Health", {})
                .get("Status", "unknown")
            )

            print(
                f"{role}: status={status}, health={health}"
            )

    expected_keys = {
        (resource_type, role)
        for resource_type, role, _ in resources
    }

    for key in registered.keys() - expected_keys:
        print(
            "Неожиданная запись в реестре:",
            key,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Диагностика и восстановление "
            "тестовых сред FastAPI + PostgreSQL"
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Восстановить полностью исправные среды",
    )

    args = parser.parse_args(argv)

    environments = get_unfinished_environments()

    if not environments:
        print(
            "Незавершённых развёртываний "
            "FastAPI + PostgreSQL нет."
        )
        return 0

    print(
        "Найдено незавершённых развёртываний: "
        f"{len(environments)}"
    )

    if args.apply:
        print("Режим восстановления: --apply")
    else:
        print("Режим диагностики: изменения не выполняются")

    client = docker.from_env()
    failures = 0

    try:
        if not client.ping():
            raise RuntimeError("Docker Engine недоступен")

        for environment in environments:
            environment_id = environment["id"]

            if not args.apply:
                inspect_environment(client, environment)
                continue

            try:
                recovered = recover_ready_environment(
                    client,
                    environment_id,
                )

                if not recovered:
                    failures += 1

            except Exception as error:
                failures += 1
                print(
                    f"Среда №{environment_id}: "
                    "ошибка восстановления "
                    f"({type(error).__name__})."
                )

    finally:
        client.close()

    return 1 if failures else 0


def check_recovery_readiness(client, environment, records=None):
    environment_id = environment["id"]
    names = get_resource_names(environment_id)

    def reject(reason):
        return {
            "ready": False,
            "reason": reason,
        }

    specifications = (
        ("network", "network", client.networks.get),
        ("volume", "volume", client.volumes.get),
        ("container", "postgres", client.containers.get),
        ("container", "api", client.containers.get),
    )

    resources = {}

    # 1. Проверяем наличие и принадлежность Docker-ресурсов.
    for resource_type, role, getter in specifications:
        try:
            resource = getter(names[role])
            resource.reload()
        except NotFound:
            return reject(f"{role}: Docker-ресурс отсутствует")

        if not is_managed_resource(
            resource,
            environment_id,
            role,
            names[role],
        ):
            return reject(
                f"{role}: проверка принадлежности не пройдена"
            )

        resources[role] = resource

    # 2. Проверяем состояние контейнеров.
    for role in ("postgres", "api"):
        container = resources[role]

        health = (
            container.attrs.get("State", {})
            .get("Health", {})
            .get("Status")
        )

        if container.status != "running" or health != "healthy":
            return reject(
                f"{role}: контейнер не готов "
                f"(status={container.status}, health={health})"
            )

    # 3. Проверяем подключение к правильной Docker-сети.
    network_id = resources["network"].id

    for role in ("postgres", "api"):
        networks = (
            resources[role].attrs
            .get("NetworkSettings", {})
            .get("Networks") or {}
        )

        attachment = networks.get(names["network"]) or {}

        if attachment.get("NetworkID") != network_id:
            return reject(
                f"{role}: неправильное подключение к Docker-сети"
            )

    # 4. Проверяем подключение постоянного тома PostgreSQL.
    mounts = resources["postgres"].attrs.get("Mounts") or []

    valid_volume = any(
        mount.get("Type") == "volume"
        and mount.get("Name") == names["volume"]
        and mount.get("Destination") == "/var/lib/postgresql"
        for mount in mounts
    )

    if not valid_volume:
        return reject(
            "postgres: не подтверждено подключение Docker Volume"
        )

    # 5. Проверяем порт FastAPI.
    bindings = (
        resources["api"].attrs
        .get("NetworkSettings", {})
        .get("Ports") or {}
    ).get("8000/tcp") or []

    if len(bindings) != 1:
        return reject("api: неправильная конфигурация порта")

    binding = bindings[0]
    port = str(binding.get("HostPort", ""))

    if (
        binding.get("HostIp") != "127.0.0.1"
        or not port.isascii()
        or not port.isdigit()
        or not 1 <= int(port) <= 65535
    ):
        return reject("api: порт не прошёл проверку безопасности")

    # 6. Сопоставляем Docker с записями PostgreSQL.
    if records is None:
      records = get_environment_resources(environment_id)

    expected = {
        ("network", "network"): "network",
        ("volume", "volume"): "volume",
        ("container", "postgres"): "postgres",
        ("container", "api"): "api",
    }

    registered = set()

    for record in records:
        key = (record["resource_type"], record["role"])

        if key not in expected or key in registered:
            return reject("Неожиданные записи в реестре ресурсов")

        role = expected[key]

        if record["resource_name"] != names[role]:
            return reject(
                f"{role}: имя в PostgreSQL не совпадает с Docker"
            )

        if key[0] == "container":
            if record["docker_id"] != resources[role].id:
                return reject(
                    f"{role}: Docker ID не совпадает с PostgreSQL"
                )
        elif record["docker_id"] is not None:
            return reject(
                f"{role}: неожиданный Docker ID в реестре"
            )

        registered.add(key)

    missing_roles = [
        role
        for key, role in expected.items()
        if key not in registered
    ]

    return {
      "ready": True,
      "reason": "Все Docker-ресурсы прошли проверку",
      "api_id": resources["api"].id,
      "postgres_id": resources["postgres"].id,
      "host_port": int(port),
      "missing_roles": missing_roles,
  }


def recover_ready_environment(client, environment_id: int) -> bool:
    names = get_resource_names(environment_id)

    resource_types = {
        "network": "network",
        "volume": "volume",
        "postgres": "container",
        "api": "container",
    }

    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        environment = connection.execute(
            text("""
                SELECT id, name
                FROM environments
                WHERE id = :environment_id
                  AND template = 'fastapi-postgres'
                  AND status = 'deploying'
                  AND owner_id IS NOT NULL
                  AND container_id IS NULL
                  AND host_port IS NULL
                FOR UPDATE
            """),
            {"environment_id": environment_id},
        ).mappings().first()

        if environment is None:
            print(
                f"Среда №{environment_id}: "
                "состояние изменилось, восстановление пропущено."
            )
            return False

        records = connection.execute(
            text("""
                SELECT
                    resource_type,
                    role,
                    resource_name,
                    docker_id
                FROM environment_resources
                WHERE environment_id = :environment_id
                ORDER BY id
            """),
            {"environment_id": environment_id},
        ).mappings().all()

        # Повторно проверяем Docker при заблокированной
        # записи тестовой среды.
        readiness = check_recovery_readiness(
            client,
            dict(environment),
            records=[dict(record) for record in records],
        )

        if not readiness["ready"]:
            print(
                f"Среда №{environment_id}: "
                f"{readiness['reason']}"
            )
            return False

        api_id = readiness["api_id"]
        postgres_id = readiness["postgres_id"]
        host_port = readiness["host_port"]

        for docker_id in (api_id, postgres_id):
            if not isinstance(docker_id, str) or not re.fullmatch(
                r"[0-9a-f]{64}", docker_id
            ):
                raise RuntimeError(
                    "Некорректный Docker ID при восстановлении"
                )

        # Регистрируем отсутствующие ресурсы в рамках
        # той же транзакции.
        for role in readiness["missing_roles"]:
            if role not in resource_types:
                raise RuntimeError(
                    f"Неизвестная роль ресурса: {role}"
                )

            docker_id = None

            if role == "api":
                docker_id = api_id
            elif role == "postgres":
                docker_id = postgres_id

            result = connection.execute(
                text("""
                    INSERT INTO environment_resources (
                        environment_id,
                        resource_type,
                        role,
                        resource_name,
                        docker_id
                    )
                    VALUES (
                        :environment_id,
                        :resource_type,
                        :role,
                        :resource_name,
                        :docker_id
                    )
                """),
                {
                    "environment_id": environment_id,
                    "resource_type": resource_types[role],
                    "role": role,
                    "resource_name": names[role],
                    "docker_id": docker_id,
                },
            )

            if result.rowcount != 1:
                raise RuntimeError(
                    f"Не удалось зарегистрировать ресурс {role}"
                )

        # Завершаем восстановление только при наличии
        # всех четырёх записей.
        result = connection.execute(
            text("""
                UPDATE environments AS e
                SET status = 'running',
                    container_id = :api_id,
                    host_port = :host_port
                WHERE e.id = :environment_id
                  AND e.template = 'fastapi-postgres'
                  AND e.status = 'deploying'
                  AND e.owner_id IS NOT NULL
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
                "api_id": api_id,
                "host_port": host_port,
            },
        )

        if result.rowcount != 1:
            raise RuntimeError(
                "Не удалось завершить восстановление среды"
            )

    print(
        f"Среда №{environment_id} восстановлена: "
        f"running, порт {host_port}"
    )

    return True


if __name__ == "__main__":
    raise SystemExit(main())