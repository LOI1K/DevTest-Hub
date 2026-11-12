import docker
from sqlalchemy import text

from worker.database import engine


def claim_job():
    query = text("""
        WITH next_job AS (
            SELECT id
            FROM environments
            WHERE status = 'pending'
                AND template = 'nginx'
                AND owner_id IS NOT NULL
            ORDER BY id
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        UPDATE environments AS e
        SET status = 'deploying'
        FROM next_job
        WHERE e.id = next_job.id
        RETURNING e.id, e.name, e.template, e.owner_id
    """)

    with engine.begin() as connection:
        job = connection.execute(query).mappings().first()
        return dict(job) if job else None


def update_status(
    job_id: int,
    status: str,
    container_id: str | None = None,
    host_port: int | None = None,
) -> None:
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                UPDATE environments
                SET status = :status,
                    container_id = :container_id,
                    host_port = :host_port
                WHERE id = :job_id
            """),
            {
                "job_id": job_id,
                "status": status,
                "container_id": container_id,
                "host_port": host_port,
            },
        )

        if result.rowcount != 1:
            raise RuntimeError(
                f"Не удалось обновить среду №{job_id}"
            )


def main():
    job = claim_job()

    if job is None:
        print("Ожидающих заданий нет.")
        return

    print(f"Получена заявка №{job['id']}: {job['name']}")
    print(f"Шаблон: {job['template']}")

    client = None
    container = None

    try:
        if job["template"] != "nginx":
            raise ValueError("Шаблон не поддерживается")

        client = docker.from_env()

        container = client.containers.run(
            image="nginx:alpine",
            name=f"devtest-hub-env-{job['id']}",
            detach=True,
            ports={"80/tcp": ("127.0.0.1", None)},
            mem_limit="128m",
            nano_cpus=500_000_000,
            pids_limit=64,
            security_opt=["no-new-privileges:true"],
            labels={
                "devtest-hub.managed": "true",
                "devtest-hub.environment-id": str(job["id"]),
            },
        )

        container.reload()

        if container.status != "running":
            raise RuntimeError("Контейнер не запущен")

        bindings = container.attrs["NetworkSettings"]["Ports"]["80/tcp"]

        if not bindings:
            raise RuntimeError("Не удалось определить порт контейнера")

        host_port = bindings[0]["HostPort"]

        update_status(
          job_id=job["id"],
          status="running",
          container_id=container.id,
          host_port=int(host_port),
        )

        print("Контейнер:", container.name)
        print("Docker ID:", container.short_id)
        print("Статус: running")
        print(f"Адрес: http://127.0.0.1:{host_port}")

    except Exception as error:
        print("Ошибка запуска:", error)

        if container is not None:
            try:
                container.remove(force=True)
            except Exception as cleanup_error:
                print("Ошибка очистки:", cleanup_error)

        update_status(job["id"], "failed")
        raise

    finally:
        if client is not None:
            client.close()


if __name__ == "__main__":
    main()
