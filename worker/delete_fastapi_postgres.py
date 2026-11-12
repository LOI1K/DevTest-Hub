import re

from docker.errors import NotFound

from worker.deploy_fastapi_postgres import (
    get_resource_names,
    is_managed_resource,
)


RESOURCE_TYPES = {
    "api": "container",
    "postgres": "container",
    "network": "network",
    "volume": "volume",
}

DELETE_ORDER = ("api", "postgres", "network", "volume")


def validate_registry(environment_id, records):
    names = get_resource_names(environment_id)
    registered = {}

    for record in records:
        role = record.get("role")

        if role not in RESOURCE_TYPES or role in registered:
            raise RuntimeError(
                "Реестр содержит неизвестную или повторную роль"
            )

        if (
            record.get("resource_type") != RESOURCE_TYPES[role]
            or record.get("resource_name") != names[role]
        ):
            raise RuntimeError(
                f"Некорректная регистрация ресурса: {role}"
            )

        docker_id = record.get("docker_id")

        if RESOURCE_TYPES[role] == "container":
            if not isinstance(docker_id, str) or not re.fullmatch(
                r"[0-9a-f]{64}", docker_id
            ):
                raise RuntimeError(
                    f"Некорректный Docker ID в реестре: {role}"
                )
        elif docker_id is not None:
            raise RuntimeError(
                f"Лишний Docker ID в реестре: {role}"
            )

        registered[role] = record

    if set(registered) != set(RESOURCE_TYPES):
        raise RuntimeError(
            "В реестре должны присутствовать все четыре ресурса"
        )

    return registered


def lookup_verified_resource(
    client,
    environment_id,
    role,
    registered,
):
    names = get_resource_names(environment_id)

    getters = {
        "api": client.containers.get,
        "postgres": client.containers.get,
        "network": client.networks.get,
        "volume": client.volumes.get,
    }

    try:
        resource = getters[role](names[role])
        resource.reload()
    except NotFound:
        return None

    if not is_managed_resource(
        resource,
        environment_id,
        role,
        names[role],
    ):
        raise RuntimeError(
            f"Ресурс {role} не принадлежит данной среде"
        )

    if role in {"api", "postgres"}:
        if resource.id != registered[role]["docker_id"]:
            raise RuntimeError(
                f"Не совпадает Docker ID ресурса {role}"
            )

    return resource


def build_deletion_plan(client, environment_id, records):
    registered = validate_registry(environment_id, records)

    resources = {
        role: lookup_verified_resource(
            client,
            environment_id,
            role,
            registered,
        )
        for role in DELETE_ORDER
    }

    network = resources["network"]

    if network is not None:
        connected = network.attrs.get("Containers") or {}

        if not isinstance(connected, dict):
            raise RuntimeError(
                "Не удалось проверить подключения Docker-сети"
            )

        allowed_ids = {
            registered["api"]["docker_id"],
            registered["postgres"]["docker_id"],
        }

        foreign_ids = set(connected) - allowed_ids

        if foreign_ids:
            raise RuntimeError(
                "К сети подключены посторонние контейнеры"
            )

    return registered, resources


def delete_registered_resources(
    client,
    environment_id: int,
    records: list[dict],
    *,
    delete_volume: bool = False,
) -> list[str]:
    if type(delete_volume) is not bool:
        raise ValueError("delete_volume должен быть bool")

    # Сначала проверяем всю инфраструктуру.
    registered, _ = build_deletion_plan(
        client,
        environment_id,
        records,
    )

    removed = []

    for role in DELETE_ORDER:
        if role == "volume" and not delete_volume:
            continue

        # Повторно проверяем объект непосредственно
        # перед его удалением.
        resource = lookup_verified_resource(
            client,
            environment_id,
            role,
            registered,
        )

        if resource is None:
            continue

        if role in {"api", "postgres"}:
            if resource.status == "running":
                resource.stop(timeout=10)

            # Именованные Docker Volume не удаляем
            # вместе с контейнерами.
            resource.remove(v=False)

        elif role == "network":
            connected = resource.attrs.get("Containers") or {}

            if connected:
                raise RuntimeError(
                    "Docker-сеть всё ещё используется. "
                    "Удаление остановлено."
                )

            resource.remove()

        elif role == "volume":
            # Только при явно указанном delete_volume=True.
            # Никогда не используем force.
            resource.remove(force=False)

        removed.append(role)

    return removed
