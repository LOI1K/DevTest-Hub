import docker
from docker.errors import DockerException

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from worker.database import engine
from worker.recover_fastapi_postgres import (
    check_recovery_readiness,
)


def get_running_environments() -> list[dict]:
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        rows = connection.execute(
            text("""
                SELECT
                    id,
                    name,
                    template,
                    status,
                    container_id,
                    host_port
                FROM environments
                WHERE template = 'fastapi-postgres'
                  AND status = 'running'
                  AND owner_id IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

    return [dict(row) for row in rows]


def inspect_running_environment(
    client,
    environment: dict,
) -> dict:
    if (
        environment.get("template") != "fastapi-postgres"
        or environment.get("status") != "running"
    ):
        raise ValueError(
            "Мониторинг поддерживает только работающие "
            "среды FastAPI + PostgreSQL"
        )

    def report(state, reason, actual_port=None):
        return {
            "state": state,
            "reason": reason,
            "actual_port": actual_port,
        }

    try:
        readiness = check_recovery_readiness(
            client,
            {
                "id": environment["id"],
                "name": environment["name"],
            },
        )

    except (DockerException, SQLAlchemyError, OSError) as error:
        # Недоступность Docker или БД не означает,
        # что тестовая среда действительно сломалась.
        return report(
            "unknown",
            "Не удалось проверить инфраструктуру: "
            f"{type(error).__name__}",
        )

    if not readiness["ready"]:
        return report(
            "degraded",
            readiness["reason"],
        )

    # Работающая среда должна иметь все четыре
    # зарегистрированных Docker-ресурса.
    if readiness["missing_roles"]:
        return report(
            "degraded",
            "Отсутствуют регистрационные записи: "
            + ", ".join(readiness["missing_roles"]),
        )

    # Проверяем, что API-контейнер совпадает
    # с сохранённым в environments Docker ID.
    if environment["container_id"] != readiness["api_id"]:
        return report(
            "degraded",
            "Docker ID FastAPI не совпадает с записью среды",
        )

    actual_port = readiness["host_port"]
    stored_port = environment["host_port"]

    # Docker Desktop может переназначить порт
    # после перезапуска контейнера или Docker Engine.
    if stored_port != actual_port:
        return report(
            "port_changed",
            f"Порт изменился: {stored_port} → {actual_port}",
            actual_port,
        )

    return report(
        "healthy",
        "FastAPI, PostgreSQL, сеть и том исправны",
        actual_port,
    )


def update_host_port(
    environment: dict,
    new_port: int,
) -> bool:
    if type(new_port) is not int or not 1 <= new_port <= 65535:
        raise ValueError("Некорректный порт FastAPI")

    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        result = connection.execute(
            text("""
                UPDATE environments
                SET host_port = :new_port
                WHERE id = :environment_id
                  AND template = 'fastapi-postgres'
                  AND status = 'running'
                  AND owner_id IS NOT NULL
                  AND container_id = :container_id
                  AND host_port = :old_port
            """),
            {
                "environment_id": environment["id"],
                "container_id": environment["container_id"],
                "old_port": environment["host_port"],
                "new_port": new_port,
            },
        )

    return result.rowcount == 1


def main(apply: bool = False) -> int:
    environments = get_running_environments()

    if not environments:
        print("Запущенных сред FastAPI + PostgreSQL нет.")
        return 0

    print(
        "Найдено работающих сред FastAPI + PostgreSQL: "
        f"{len(environments)}"
    )

    if apply:
        print("Режим мониторинга: синхронизация портов")
    else:
        print("Режим мониторинга: только чтение")

    client = docker.from_env()

    try:
        for environment in environments:
            result = inspect_running_environment(
                client,
                environment,
            )

            print(
                f"\nСреда №{environment['id']} "
                f"({environment['name']}): "
                f"{result['state']}"
            )
            print(result["reason"])

            if result["state"] != "port_changed":
                continue

            new_port = result["actual_port"]

            if not apply:
                print(
                    "План: обновить порт "
                    f"{environment['host_port']} → {new_port}"
                )
                continue

            # Повторная проверка Docker перед записью в БД.
            confirmation = inspect_running_environment(
                client,
                environment,
            )

            if (
                confirmation["state"] != "port_changed"
                or confirmation["actual_port"] != new_port
            ):
                print(
                    "Состояние инфраструктуры изменилось. "
                    "Обновление порта пропущено."
                )
                continue

            if update_host_port(environment, new_port):
                print(
                    f"Порт FastAPI обновлён в PostgreSQL: "
                    f"{new_port}"
                )
            else:
                print(
                    "Запись среды изменилась. "
                    "Обновление порта пропущено."
                )

    finally:
        client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
