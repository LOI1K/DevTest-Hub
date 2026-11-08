import argparse
import time

import signal
from threading import Event

from sqlalchemy import text

from worker.database import engine
from worker.delete_once import delete_environment
from worker.run_once import main as run_deployment
from worker.recover_once import recover_jobs


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
                ORDER BY id
            """)
        ).scalars().all()

        has_pending = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM environments
                    WHERE status = 'pending'
                      AND owner_id IS NOT NULL
                )
            """)
          ).scalar_one()

    return deleting_ids, has_pending


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
                recover_jobs(apply=True)

                if args.once:
                    if not stop_requested.is_set():
                        process_jobs()
                    return

                print(f"Интервал проверки: {args.interval} сек.")

                while not stop_requested.is_set():
                    try:
                        process_jobs()
                    except Exception as error:
                        print(f"Ошибка цикла Worker: {error}")

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
