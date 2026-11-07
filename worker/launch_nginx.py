import docker


CONTAINER_NAME = "devtest-hub-worker-smoke-nginx"
HOST_PORT = 18080


def main():
    client = docker.from_env()

    try:
        print("Создание тестового nginx-контейнера...")

        container = client.containers.run(
            image="nginx:alpine",
            name=CONTAINER_NAME,
            detach=True,
            ports={
                "80/tcp": ("127.0.0.1", HOST_PORT),
            },
            mem_limit="128m",
            nano_cpus=500_000_000,
            pids_limit=64,
            security_opt=["no-new-privileges:true"],
            labels={
                "devtest-hub.managed": "true",
                "devtest-hub.purpose": "smoke-test",
            },
        )

        container.reload()

        print("Контейнер:", container.name)
        print("ID:", container.short_id)
        print("Статус:", container.status)
        print(f"Адрес: http://127.0.0.1:{HOST_PORT}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
