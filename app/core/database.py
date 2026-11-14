from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.models.base import Base


def create_database(settings: Settings) -> tuple[Engine, sessionmaker[Session]]:
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    options: dict[str, object] = {"connect_args": connect_args, "pool_pre_ping": True}
    if settings.database_url in {"sqlite://", "sqlite:///:memory:"}:
        options["poolclass"] = StaticPool
    elif settings.database_url.startswith("sqlite"):
        database_path = make_url(settings.database_url).database
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url, **options)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return engine, factory


def initialize_database(engine: Engine) -> None:
    Base.metadata.create_all(bind=engine)


def session_scope(factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    session = factory()
    try:
        yield session
    finally:
        session.close()
