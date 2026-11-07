import docker
from docker.errors import NotFound
from sqlalchemy import text

from worker.database import engine


def main():
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        environments = connection.execute(
            text("""
                SELECT id, name, status, container_id, host_port
                FROM environments
                WHERE container_id IS NOT NULL
                ORDER BY id
            """)
        ).mappings().all()

    client = docker.from_env()

    try:
        for environment in environments:
            env_id = environment["id"]

            try:
                container = client.containers.get(
                    environment["container_id"]
                )
                container.reload()
            except NotFound:
                print(f"Среда №{env_id}: контейнер не найден")
                continue

            valid_owner = (
                container.name == f"devtest-hub-env-{env_id}"
                and container.labels.get("devtest-hub.managed") == "true"
                and container.labels.get(
                    "devtest-hub.environment-id"
                ) == str(env_id)
            )

            bindings = (
                container.attrs["NetworkSettings"]["Ports"]
                .get("80/tcp") or []
            )
            actual_port = (
                int(bindings[0]["HostPort"])
                if bindings else None
            )

            valid_port = actual_port == environment["host_port"]

            print(f"\nСреда №{env_id}: {environment['name']}")
            print("Контейнер:", container.name)
            print("Статус Docker:", container.status)
            print("Порт:", actual_port)
            print(
                "Проверка:",
                "OK" if valid_owner and valid_port else "НЕСООТВЕТСТВИЕ",
            )

    finally:
        client.close()


if __name__ == "__main__":
    main()
