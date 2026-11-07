import argparse
import time

from sqlalchemy import text

from app.database import engine
from worker.delete_once import delete_environment
from worker.run_once import main as run_deployment


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

    if not deleting_ids and not has_pending:
        print("Ожидающих заданий нет.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--interval", type=int, default=5)

    args = parser.parse_args()

    if args.interval < 1:
        parser.error("Интервал должен быть не менее 1 секунды")

    if args.once:
        process_jobs()
        return

    print("Docker Worker запущен.")
    print(f"Интервал проверки: {args.interval} сек.")

    try:
        while True:
            try:
                process_jobs()
            except Exception as error:
                print(f"Ошибка цикла Worker: {error}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\nDocker Worker остановлен.")


if __name__ == "__main__":
    main()
