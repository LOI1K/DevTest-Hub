import sys
from pathlib import Path
from logging.config import fileConfig

from alembic import context


# Добавляем backend в пути поиска Python
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.database import engine
from app.models import Base


config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ORM-модели, по которым Alembic определяет структуру БД
target_metadata = Base.metadata


def run_migrations_offline():
    url = engine.url.render_as_string(hide_password=False)

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
