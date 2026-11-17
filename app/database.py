from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import ensure_directories, get_settings

class Base(DeclarativeBase):
    pass

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None

def _configure_sqlite(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        ensure_directories(settings)
        url = settings.database_url
        kwargs: dict = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            _configure_sqlite(_engine)
    return _engine

def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _session_factory

def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()

def _ensure_runtime_columns(engine: Engine) -> None:
    """Добавляет недостающие колонки в уже существующие БД.

    create_all() не изменяет существующие таблицы, поэтому при обновлении
    проекта старые базы должны получать новые поля без ручного вмешательства.
    """
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "items" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("items")}
    if "ai_mode" in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE items ADD COLUMN ai_mode VARCHAR(16) DEFAULT 'auto' NOT NULL")
        )

def init_db() -> None:
    from . import models

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_runtime_columns(engine)

def reset_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
