from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, URL, create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeDecorator


def make_engine(path: Path) -> Engine:
    engine = create_engine(
        URL.create("sqlite", database=str(path.resolve())),
        connect_args={"timeout": 5},
        hide_parameters=True,
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON").close()

    return engine


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UtcDateTime(TypeDecorator):
    """Store UTC consistently and restore timezone information on SQLite reads."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.utcoffset() is None:
            raise ValueError("Timestamp must have a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        return value.replace(tzinfo=timezone.utc) if value is not None else None
