import docker
from sqlalchemy import text
from docker.errors import NotFound

from worker.database import engine
from worker.deploy_fastapi_postgres import get_resource_names
from worker.delete_fastapi_postgres import (
    build_deletion_plan,
    delete_registered_resources,
)


def verify_no_unregistered_resources(
    client,
    environment_id: int,
) -> None:
    names = get_resource_names(environment_id)

    getters = {
        "api": client.containers.get,
        "postgres": client.containers.get,
        "network": client.networks.get,
        "volume": client.volumes.get,
    }

    for role, getter in getters.items():
        try:
            getter(names[role])
        except NotFound:
            continue

        raise RuntimeError(
            f"В Docker найден незарегистрированный ресурс: "
            f"{names[role]}. Автоматическое удаление запрещено."
        )


def delete_fastapi_environment(
    environment_id: int,
    *,
    apply: bool = False,
    delete_volume: bool = False,
) -> bool:
    get_resource_names(environment_id)

    if type(apply) is not bool or type(delete_volume) is not bool:
        raise ValueError("Некорректные параметры удаления")

    if apply and not delete_volume:
        raise RuntimeError(
            "Полное удаление требует явного "
            "разрешения delete_volume=True"
        )

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
                  AND status = 'deleting'
                  AND owner_id IS NOT NULL
                  AND delete_volume_on_delete IS TRUE
                FOR UPDATE SKIP LOCKED
            """),
            {"environment_id": environment_id},
        ).mappings().first()

        if environment is None:
            print(
                f"Среда №{environment_id} не найдена "
                "или не ожидает удаления."
            )
            return False

        rows = connection.execute(
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

        records = [dict(row) for row in rows]

        client = docker.from_env()

        try:
            if not client.ping():
                raise RuntimeError("Docker Engine недоступен")

            # При наличии реестра проверяем все четыре ресурса.
            # При пустом реестре убеждаемся, что в Docker
            # действительно ничего не осталось.
            if records:
                build_deletion_plan(
                    client,
                    environment_id,
                    records,
                )
            else:
                verify_no_unregistered_resources(
                    client,
                    environment_id,
                )

            if not apply:
                print(
                    f"Среда №{environment_id}: "
                    "проверка удаления пройдена."
                )
                print(
                    "Режим диагностики: "
                    "Docker и PostgreSQL не изменены."
                )
                return True

            if records:
                removed = delete_registered_resources(
                    client,
                    environment_id,
                    records,
                    delete_volume=True,
                )

                print(
                    "Удалены Docker-ресурсы:",
                    ", ".join(removed)
                    if removed else "уже отсутствовали",
                )
            else:
                print(
                    "Зарегистрированных Docker-ресурсов нет. "
                    "Удаление записи среды разрешено."
                )

        finally:
            client.close()

        # Удаляем запись только после успешного
        # завершения операций Docker.
        result = connection.execute(
            text("""
                DELETE FROM environments
                WHERE id = :environment_id
                  AND template = 'fastapi-postgres'
                  AND status = 'deleting'
                  AND owner_id IS NOT NULL
                RETURNING id
            """),
            {"environment_id": environment_id},
        )

        if result.scalar_one_or_none() != environment_id:
            raise RuntimeError(
                "Не удалось удалить запись среды"
            )

    print(
        f"Среда №{environment_id} полностью удалена."
    )
    return True
