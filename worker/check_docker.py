import docker


def main():
    client = docker.from_env()

    try:
        print("Проверка соединения с Docker Engine...")

        if client.ping():
            print("Docker Engine доступен!")

        version = client.version()
        print("Версия Docker Engine:", version["Version"])

        print("\nЗапущенные контейнеры:")

        for container in client.containers.list():
            print(f"- {container.name}: {container.status}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
