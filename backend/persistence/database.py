from pathlib import Path
import sys

SQLALCHEMY_DEPS_PATH = Path(__file__).resolve().parents[1] / ".sqlalchemy_deps"
if SQLALCHEMY_DEPS_PATH.exists():
    deps_str = str(SQLALCHEMY_DEPS_PATH)
    if deps_str not in sys.path:
        sys.path.insert(0, deps_str)

from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "chat_sessions.sqlite3"

Base = declarative_base()


def sqlite_url_for(db_path: Path) -> str:
    return f"sqlite:///{Path(db_path).resolve().as_posix()}"


def create_sqlite_engine(db_path: Path = DEFAULT_DB_PATH):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        sqlite_url_for(db_path),
        connect_args={"check_same_thread": False},
        future=True,
    )


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


engine = create_sqlite_engine()
SessionLocal = create_session_factory(engine)


def init_db(bind_engine=None):
    from . import models  # noqa: F401

    active_engine = bind_engine or engine
    Base.metadata.create_all(bind=active_engine)
    _ensure_browser_session_columns(active_engine)


def _ensure_browser_session_columns(bind_engine):
    inspector = inspect(bind_engine)
    table_columns = {
        table: {column["name"] for column in inspector.get_columns(table)}
        for table in inspector.get_table_names()
    }
    migrations = {
        "chat_sessions": "ALTER TABLE chat_sessions ADD COLUMN browser_session_id VARCHAR(64)",
        "chat_runs": "ALTER TABLE chat_runs ADD COLUMN browser_session_id VARCHAR(64)",
        "chat_stream_events": "ALTER TABLE chat_stream_events ADD COLUMN browser_session_id VARCHAR(64)",
    }
    with bind_engine.begin() as connection:
        for table, statement in migrations.items():
            if table in table_columns and "browser_session_id" not in table_columns[table]:
                connection.execute(text(statement))
