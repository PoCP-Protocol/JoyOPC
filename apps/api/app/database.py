from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from .config import DATABASE_URL

_is_sqlite = DATABASE_URL.startswith("sqlite")
_engine_kwargs: dict = {
    "future": True,
    "pool_pre_ping": True,
}
if _is_sqlite:
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
    if ":memory:" in DATABASE_URL or DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        _engine_kwargs["poolclass"] = StaticPool
else:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
