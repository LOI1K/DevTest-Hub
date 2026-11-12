import re

from sqlalchemy import text

from worker.database import engine


RESOURCE_TYPES = {"container", "network", "volume"}


def register_resource(
    environment_id: int,
    resource_type: str,
    role: str,
    resource_name: str,
    docker_id: str | None = None,
) -> int:
    if resource_type not in RESOURCE_TYPES:
        raise ValueError("Недопустимый тип Docker-ресурса")

    if not role or len(role) > 40:
        raise ValueError("Некорректная роль ресурса")

    if not resource_name or len(resource_name) > 128:
        raise ValueError("Некорректное имя ресурса")

    if docker_id is not None and not re.fullmatch(
        r"[0-9a-f]{64}",
        docker_id,
    ):
        raise ValueError("Некорректный Docker ID")

    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Регистрация ресурсов разрешена только "
                "в основной базе данных"
            )

        result = connection.execute(
            text("""
                INSERT INTO environment_resources (
                    environment_id,
                    resource_type,
                    role,
                    resource_name,
                    docker_id
                )
                SELECT
                    e.id,
                    :resource_type,
                    :role,
                    :resource_name,
                    :docker_id
                FROM environments AS e
                WHERE e.id = :environment_id
                  AND e.template = 'fastapi-postgres'
                  AND e.status = 'deploying'
                RETURNING id
            """),
            {
                "environment_id": environment_id,
                "resource_type": resource_type,
                "role": role,
                "resource_name": resource_name,
                "docker_id": docker_id,
            },
        )

        resource_id = result.scalar_one_or_none()

        if resource_id is None:
            raise RuntimeError(
                f"Среда №{environment_id} не найдена "
                "или не находится в состоянии deploying"
            )

        return resource_id


def get_environment_resources(environment_id: int) -> list[dict]:
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        resources = connection.execute(
            text("""
                SELECT
                    id,
                    environment_id,
                    resource_type,
                    role,
                    resource_name,
                    docker_id
                FROM environment_resources
                WHERE environment_id = :environment_id
                ORDER BY id DESC
            """),
            {"environment_id": environment_id},
        ).mappings().all()

    return [dict(resource) for resource in resources]


def clear_deployment_records(environment_id: int) -> None:
    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        connection.execute(
            text("""
                DELETE FROM environment_resources AS r
                USING environments AS e
                WHERE r.environment_id = e.id
                  AND e.id = :environment_id
                  AND e.template = 'fastapi-postgres'
                  AND e.status = 'deploying'
            """),
            {"environment_id": environment_id},
        )
