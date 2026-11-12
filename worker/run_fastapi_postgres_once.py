import docker
from sqlalchemy import text

from worker.database import engine
from worker.deploy_fastapi_postgres import deploy_environment


def claim_fastapi_job():
    with engine.begin() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        job = connection.execute(
            text("""
                WITH next_job AS (
                    SELECT id
                    FROM environments
                    WHERE status = 'pending'
                      AND template = 'fastapi-postgres'
                      AND owner_id IS NOT NULL
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE environments AS e
                SET status = 'deploying'
                FROM next_job
                WHERE e.id = next_job.id
                RETURNING
                    e.id,
                    e.name,
                    e.template,
                    e.owner_id
            """)
        ).mappings().first()

    return dict(job) if job else None


def main():
    job = claim_fastapi_job()

    if job is None:
        print("Ожидающих заявок FastAPI + PostgreSQL нет.")
        return False

    environment_id = job["id"]

    print(
        f"Развёртывание среды №{environment_id}: "
        f"{job['name']}"
    )

    client = None

    try:
        client = docker.from_env()

        if not client.ping():
            raise RuntimeError("Docker Engine недоступен")

        api_id, host_port = deploy_environment(
            client,
            environment_id,
        )

        print(
            f"Среда №{environment_id} работает "
            f"на порту {host_port}"
        )

        return True

    except Exception as error:
        # Не переводим среду в failed автоматически:
        # часть Docker-ресурсов могла сохраниться.
        # Незавершённую среду проверит механизм восстановления.
        print(
            f"Развёртывание среды №{environment_id} "
            f"не завершено: {type(error).__name__}"
        )

        raise

    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
