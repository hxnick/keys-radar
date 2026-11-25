from alembic import context

from radar.config import Settings
from radar.db import make_engine
from radar.models import Base


def run_migrations():
    if context.is_offline_mode():
        context.configure(dialect_name="sqlite", target_metadata=Base.metadata, literal_binds=True)
        with context.begin_transaction():
            context.run_migrations()
        return

    path = context.config.attributes.get("database_path")
    if path is None:
        path = Settings().database_path
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = make_engine(path)
    try:
        with engine.begin() as connection:
            # SQLite in Python 3.11 needs an explicit BEGIN to make DDL transactional.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            context.configure(connection=connection, target_metadata=Base.metadata)
            context.run_migrations()
    finally:
        engine.dispose()


run_migrations()
