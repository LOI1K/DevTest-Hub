import re
import argparse

import docker
from docker.errors import NotFound
from sqlalchemy import text

from worker.database import engine


def get_running_environments():
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        environments = connection.execute(
            text("""
                SELECT id, name, container_id, host_port
                FROM environments
                WHERE status = 'running'
                ORDER BY id
            """)
        ).mappings().all()

    return [dict(environment) for environment in environments]


def check_environment(client, environment):
    environment_id = environment["id"]
    container_id = environment["container_id"]
    host_port = environment["host_port"]

    expected_name = f"devtest-hub-env-{environment_id}"

    if (
        not isinstance(container_id, str)
        or not re.fullmatch(r"[0-9a-f]{64}", container_id)
        or not isinstance(host_port, int)
        or not 1 <= host_port <= 65535
    ):
        return "НЕСООТВЕТСТВИЕ: отсутствуют корректные Docker-метаданные"

    try:
        container = client.containers.get(container_id)
        container.reload()

    except NotFound:
        try:
            client.containers.get(expected_name)
        except NotFound:
            return "ОШИБКА: Docker-контейнер отсутствует"

        return "НЕСООТВЕТСТВИЕ: найден контейнер с другим Docker ID"

    labels = container.labels or {}

    valid_owner = (
        container.id == container_id
        and container.name == expected_name
        and labels.get("devtest-hub.managed") == "true"
        and labels.get("devtest-hub.environment-id") == str(environment_id)
    )

    if not valid_owner:
        return "НЕСООТВЕТСТВИЕ: контейнер не прошёл проверку принадлежности"

    if container.status != "running":
        return f"ОШИБКА: Docker-контейнер имеет статус {container.status}"

    bindings = (
        container.attrs.get("NetworkSettings", {})
        .get("Ports") or {}
    ).get("80/tcp") or []

    if len(bindings) != 1:
        return "НЕСООТВЕТСТВИЕ: некорректная конфигурация портов"

    binding = bindings[0]

    if (
        binding.get("HostIp") != "127.0.0.1"
        or str(binding.get("HostPort")) != str(host_port)
    ):
        return "НЕСООТВЕТСТВИЕ: порт Docker не совпадает с PostgreSQL"

    return f"OK: контейнер работает, порт {host_port}"


def mark_failed(environment):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                UPDATE environments
                SET status = 'failed'
                WHERE id = :id
                  AND status = 'running'
                  AND container_id = :container_id
                  AND host_port = :host_port
            """),
            {
                "id": environment["id"],
                "container_id": environment["container_id"],
                "host_port": environment["host_port"],
            },
        )

    return result.rowcount == 1


def main(apply=False):
    environments = get_running_environments()

    if not environments:
        print("Работающих тестовых сред нет.")
        return

    print(
        f"Найдено работающих сред в PostgreSQL: "
        f"{len(environments)}"
    )

    if apply:
        print("Режим применения изменений")
    else:
        print("Режим проверки: изменения не выполняются")

    client = docker.from_env()

    try:
        if not client.ping():
            raise RuntimeError("Docker Engine недоступен")

        for environment in environments:
            print(
                f"\nСреда №{environment['id']}: "
                f"{environment['name']}"
            )

            result = check_environment(client, environment)
            print("Проверка:", result)

            failure_detected = (
                result == "ОШИБКА: Docker-контейнер отсутствует"
                or result in (
                    "ОШИБКА: Docker-контейнер имеет статус exited",
                    "ОШИБКА: Docker-контейнер имеет статус dead",
                )
            )

            if not failure_detected:
                continue

            if not apply:
                print("План: установить статус failed")
                continue

            # Повторно проверяем Docker перед изменением БД.
            confirmation = check_environment(
                client,
                environment,
            )

            if confirmation != result:
                print(
                    "Состояние Docker изменилось. "
                    "Обновление пропущено."
                )
                continue

            if mark_failed(environment):
                print("Статус PostgreSQL обновлён: failed")
            else:
                print(
                    "Состояние записи изменилось. "
                    "Обновление пропущено."
                )

    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Обновить статусы неисправных сред",
    )

    args = parser.parse_args()
    main(apply=args.apply)
