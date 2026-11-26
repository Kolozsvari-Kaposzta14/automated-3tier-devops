"""Centralize engine and sessions so tests can replace the database dependency."""
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    """Shared metadata for SQLAlchemy models."""


# pool_pre_ping helps recover connections after transient database interruptions.
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    # Yield a per-request session and close it even if a handler raises an exception.
    with SessionLocal() as session:
        yield session
