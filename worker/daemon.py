import argparse
import time
import os

import signal
from threading import Event

from sqlalchemy import text

from worker.database import engine
from worker.delete_once import delete_environment
from worker.run_once import main as run_deployment
from worker.recover_once import recover_jobs
from worker.monitor import main as monitor_environments
from worker.run_fastapi_postgres_once import (
    main as run_fastapi_deployment,
)
from worker.recover_fastapi_postgres import (
    main as recover_fastapi_environments,
)
from worker.monitor_fastapi_postgres import (
    main as monitor_fastapi_environments,
)
from worker.delete_fastapi_postgres_once import (
    delete_fastapi_environment,
)


def get_jobs():
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError("Подключена не основная база данных")

        deleting_ids = connection.execute(
            text("""
                SELECT id
                FROM environments
                WHERE status = 'deleting'
                    AND template = 'nginx'
                ORDER BY id
            """)
        ).scalars().all()

        has_pending = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM environments
                    WHERE status = 'pending'
                        AND template = 'nginx'
                        AND owner_id IS NOT NULL
                )
            """)
          ).scalar_one()

    return deleting_ids, has_pending


def fastapi_enabled() -> bool:
    return (
        os.environ.get(
            "DEVTEST_HUB_ENABLE_FASTAPI_POSTGRES",
            "0",
        ) == "1"
    )


def has_fastapi_pending() -> bool:
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        result = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM environments
                    WHERE status = 'pending'
                      AND template = 'fastapi-postgres'
                      AND owner_id IS NOT NULL
                )
            """)
        ).scalar_one()

    return bool(result)


def run_startup_recovery():
    # Восстановление существующего шаблона Nginx.
    recover_jobs(apply=True)

    # Новый шаблон обрабатываем только при включённой функции.
    if not fastapi_enabled():
        return

    try:
        result = recover_fastapi_environments(["--apply"])

        if result != 0:
            print(
                "Не все среды FastAPI + PostgreSQL "
                "удалось восстановить. "
                "Они сохранены для диагностики."
            )

    except Exception as error:
        print(
            "Ошибка восстановления FastAPI + PostgreSQL: "
            f"{type(error).__name__}"
        )


def run_periodic_monitoring():
    # Существующий мониторинг Nginx.
    try:
        monitor_environments(apply=True)
    except Exception as error:
        print(
            "Ошибка мониторинга Nginx: "
            f"{type(error).__name__}"
        )

    if not fastapi_enabled():
        return

    # Новый мониторинг пока работает только на чтение.
    try:
        result = monitor_fastapi_environments(apply=True)

        if result != 0:
            print(
                "Мониторинг FastAPI + PostgreSQL "
                "завершился с ошибкой."
            )

    except Exception as error:
        print(
            "Ошибка мониторинга FastAPI + PostgreSQL: "
            f"{type(error).__name__}"
        )


def get_fastapi_deleting_ids() -> list[int]:
    with engine.connect() as connection:
        database = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database != "devtesthub":
            raise RuntimeError(
                "Подключена не основная база данных"
            )

        result = connection.execute(
            text("""
                SELECT id
                FROM environments
                WHERE template = 'fastapi-postgres'
                  AND status = 'deleting'
                  AND owner_id IS NOT NULL
                  AND delete_volume_on_delete IS TRUE
                ORDER BY id
            """)
        )

        return list(result.scalars().all())


def process_fastapi_deletions() -> None:
    if not fastapi_enabled():
        return

    try:
        environment_ids = get_fastapi_deleting_ids()
    except Exception as error:
        print(
            "Не удалось получить заявки на удаление "
            "FastAPI + PostgreSQL: "
            f"{type(error).__name__}"
        )
        return

    for environment_id in environment_ids:
        print(
            "Обнаружена заявка на удаление "
            f"FastAPI + PostgreSQL №{environment_id}."
        )

        try:
            delete_fastapi_environment(
                environment_id,
                apply=True,
                delete_volume=True,
            )
        except Exception as error:
            print(
                f"Ошибка удаления среды №{environment_id}: "
                f"{type(error).__name__}"
            )


def process_jobs():
    deleting_ids, has_pending = get_jobs()

    for environment_id in deleting_ids:
        print(f"Обработка удаления среды №{environment_id}")

        try:
            delete_environment(environment_id, apply=True)
        except Exception as error:
            print(f"Ошибка удаления №{environment_id}: {error}")

    if has_pending:
        print("Обнаружена заявка на создание среды.")

        try:
            run_deployment()
        except Exception as error:
            print(f"Ошибка развёртывания: {error}")

    # FastAPI + PostgreSQL:
    # отдельный обработчик, выключенный по умолчанию.
    if fastapi_enabled() and has_fastapi_pending():
        print(
            "Обнаружена заявка на создание "
            "FastAPI + PostgreSQL."
        )

        try:
            run_fastapi_deployment()
        except Exception as error:
            print(
                "Ошибка развёртывания FastAPI + PostgreSQL: "
                f"{type(error).__name__}"
            )

    process_fastapi_deletions()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=5)

    args = parser.parse_args()

    if args.interval < 1:
        parser.error("Интервал должен быть не менее 1 секунды")

    lock_id = 11335577
    stop_requested = Event()

    def handle_sigterm(_signum, _frame):
        stop_requested.set()

    previous_handler = signal.signal(
        signal.SIGTERM,
        handle_sigterm,
    )

    try:
        with engine.connect() as connection:
            acquired = connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"),
                {"lock_id": lock_id},
            ).scalar_one()

            connection.commit()

            if not acquired:
                print("Другой Docker Worker уже работает.")
                return

            try:
                print("Docker Worker запущен.")
                print("Эксклюзивная блокировка получена.")

                print("Проверка незавершённых развёртываний...")
                run_startup_recovery()

                if args.once:
                    if not stop_requested.is_set():
                        process_jobs()
                    return

                print(f"Интервал проверки: {args.interval} сек.")
                print("Интервал мониторинга: 60 сек.")

                next_monitor_at = 0.0

                while not stop_requested.is_set():
                    try:
                        process_jobs()
                    except Exception as error:
                        print(f"Ошибка цикла Worker: {error}")

                    if (
                        not stop_requested.is_set()
                        and time.monotonic() >= next_monitor_at
                    ):
                        next_monitor_at = time.monotonic() + 60

                        try:
                            run_periodic_monitoring()
                        except Exception as error:
                            print(
                                "Ошибка общего мониторинга: "
                                f"{type(error).__name__}"
                            )

                    stop_requested.wait(args.interval)

            except KeyboardInterrupt:
                print("\nDocker Worker остановлен через Ctrl+C.")

            finally:
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_id)"),
                    {"lock_id": lock_id},
                )
                connection.commit()

                print("Эксклюзивная блокировка освобождена.")

    finally:
        signal.signal(
            signal.SIGTERM,
            previous_handler,
        )

if __name__ == "__main__":
    main()
