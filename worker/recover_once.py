import argparse

import docker
from docker.errors import NotFound
from sqlalchemy import text

from worker.database import engine


def get_unfinished_jobs():
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        jobs = connection.execute(
            text("""
                SELECT id, name, container_id, host_port
                FROM environments
                WHERE status = 'deploying'
                  AND owner_id IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

    return [dict(job) for job in jobs]


def update_job(job_id, status, container_id=None, host_port=None):
    with engine.begin() as connection:
        result = connection.execute(
            text("""
                UPDATE environments
                SET status = :status,
                    container_id = :container_id,
                    host_port = :host_port
                WHERE id = :job_id
                  AND status = 'deploying'
                  AND container_id IS NULL
                  AND host_port IS NULL
            """),
            {
                "job_id": job_id,
                "status": status,
                "container_id": container_id,
                "host_port": host_port,
            },
        )

    if result.rowcount != 1:
        print(f"Среда №{job_id}: состояние изменилось, обновление пропущено")
        return False

    return True


def recover_jobs(apply=False):
    jobs = get_unfinished_jobs()

    if not jobs:
        print("Незавершённых развёртываний нет.")
        return

    print(f"Найдено незавершённых развёртываний: {len(jobs)}")

    client = docker.from_env()

    try:
        if not client.ping():
            raise RuntimeError("Docker Engine недоступен")

        for job in jobs:
            job_id = job["id"]
            expected_name = f"devtest-hub-env-{job_id}"

            print(f"\nПроверка среды №{job_id}: {job['name']}")

            if job["container_id"] is not None or job["host_port"] is not None:
                print("У среды уже есть Docker-метаданные. Нужна ручная проверка.")
                continue

            try:
                container = client.containers.get(expected_name)
                container.reload()
            except NotFound:
                print("Контейнер отсутствует.")

                if apply:
                    if update_job(job_id, "failed"):
                        print("Статус восстановлен: failed")
                else:
                    print("План: установить статус failed")

                continue

            labels = container.labels or {}

            valid_owner = (
                container.name == expected_name
                and labels.get("devtest-hub.managed") == "true"
                and labels.get("devtest-hub.environment-id") == str(job_id)
            )

            if not valid_owner:
                print("Контейнер не прошёл проверку принадлежности.")
                print("Изменения пропущены.")
                continue

            if container.status != "running":
                print(f"Статус Docker: {container.status}")
                print("Требуется ручная проверка контейнера.")
                continue

            bindings = (
                container.attrs.get("NetworkSettings", {})
                .get("Ports", {})
                .get("80/tcp") or []
            )

            if len(bindings) != 1:
                print("Неожиданная конфигурация портов.")
                continue

            binding = bindings[0]
            host_port = binding.get("HostPort")
            host_ip = binding.get("HostIp")

            if (
                host_ip != "127.0.0.1"
                or not str(host_port).isdigit()
                or not 1 <= int(host_port) <= 65535
            ):
                print("Порт не прошёл проверку безопасности.")
                continue

            print(f"Найден работающий контейнер: {container.name}")
            print(f"Порт: {host_port}")

            if apply:
                if update_job(
                    job_id,
                    "running",
                    container_id=container.id,
                    host_port=int(host_port),
                ):
                    print("Статус и Docker-метаданные восстановлены.")
            else:
                print("План: восстановить статус running и Docker-метаданные")

    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Применить восстановление к PostgreSQL",
    )
    args = parser.parse_args()

    if args.apply:
        print("Режим применения изменений")
    else:
        print("Режим предварительной проверки: данные не изменяются")

    recover_jobs(apply=args.apply)


if __name__ == "__main__":
    main()
