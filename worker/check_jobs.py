from sqlalchemy import text

from app.database import engine


def main():
    print("Поиск ожидающих тестовых сред...")

    query = text("""
        SELECT id, name, template, status, owner_id
        FROM environments
        WHERE status = 'pending'
          AND owner_id IS NOT NULL
        ORDER BY id
    """)

    with engine.connect() as connection:
        jobs = connection.execute(query).mappings().all()

    if not jobs:
        print("Ожидающих заданий нет.")
        return

    for job in jobs:
        print(
            f"ID: {job['id']} | "
            f"Имя: {job['name']} | "
            f"Шаблон: {job['template']} | "
            f"Статус: {job['status']} | "
            f"Владелец: {job['owner_id']}"
        )

    print(f"\nВсего заданий: {len(jobs)}")


if __name__ == "__main__":
    main()
