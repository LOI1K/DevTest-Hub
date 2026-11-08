import argparse
import re

import docker
from docker.errors import NotFound
from sqlalchemy import text

from worker.database import engine


def cleanup_container_without_metadata(
    environment_id: int,
    apply: bool,
) -> None:
    expected_name = f"devtest-hub-env-{environment_id}"
    client = docker.from_env()

    try:
        try:
            container = client.containers.get(expected_name)
        except NotFound:
            print("Контейнер с ожидаемым именем отсутствует.")
            return

        container.reload()
        labels = container.labels or {}

        valid = (
            container.name == expected_name
            and labels.get("devtest-hub.managed") == "true"
            and labels.get(
                "devtest-hub.environment-id"
            ) == str(environment_id)
        )

        if not valid:
            raise RuntimeError(
                "Контейнер не прошёл проверку принадлежности"
            )

        print(
            "Найден контейнер без Docker ID в PostgreSQL:",
            container.name,
        )

        if apply:
            if container.status == "running":
                container.stop(timeout=10)

            container.remove()
            print("Docker-контейнер удалён.")

    finally:
        client.close()


def delete_environment(environment_id: int, apply: bool) -> None:
    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        environment = connection.execute(
            text("""
                SELECT id, name, status, container_id, host_port
                FROM environments
                WHERE id = :environment_id
                FOR UPDATE SKIP LOCKED
            """),
            {"environment_id": environment_id},
        ).mappings().first()

        if environment is None:
            print("Среда не найдена или уже обрабатывается.")
            return

        print("Среда:", environment["name"])
        print("ID:", environment["id"])
        print("Статус:", environment["status"])

        if apply and environment["status"] != "deleting":
            raise RuntimeError(
                "Удаление разрешено только для статуса deleting"
            )

        container_id = environment["container_id"]

        if container_id is None and environment["host_port"] is not None:
            raise RuntimeError("Некорректные данные контейнера")

        if container_id is None:
            cleanup_container_without_metadata(
                environment_id,
                apply,
            )

        if container_id is not None:
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise RuntimeError("Некорректный Docker ID")

            client = docker.from_env()

            try:
                expected_name = f"devtest-hub-env-{environment_id}"

                try:
                    container = client.containers.get(container_id)
                except NotFound:
                    # Проверяем, не существует ли контейнер
                    # с ожидаемым именем, но другим ID.
                    try:
                        client.containers.get(expected_name)
                    except NotFound:
                        print("Контейнер уже отсутствует.")
                    else:
                        raise RuntimeError(
                            "Обнаружен контейнер с другим Docker ID"
                        )
                else:
                    container.reload()

                    valid = (
                        container.id == container_id
                        and container.name == expected_name
                        and container.labels.get(
                            "devtest-hub.managed"
                        ) == "true"
                        and container.labels.get(
                            "devtest-hub.environment-id"
                        ) == str(environment_id)
                    )

                    if not valid:
                        raise RuntimeError(
                            "Контейнер не прошёл проверку принадлежности"
                        )

                    print("Контейнер:", container.name)
                    print("Статус Docker:", container.status)

                    if apply:
                        if container.status == "running":
                            container.stop(timeout=10)

                        container.remove()
                        print("Docker-контейнер удалён.")

            finally:
                client.close()

        if not apply:
            print("Режим проверки: ничего не удалено.")
            return

        result = connection.execute(
            text("""
                DELETE FROM environments
                WHERE id = :environment_id
                  AND status = 'deleting'
            """),
            {"environment_id": environment_id},
        )

        if result.rowcount != 1:
            raise RuntimeError("Не удалось удалить запись PostgreSQL")

        print("Запись PostgreSQL удалена.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("environment_id", type=int)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Выполнить настоящее удаление",
    )

    args = parser.parse_args()
    delete_environment(args.environment_id, args.apply)


if __name__ == "__main__":
    main()
