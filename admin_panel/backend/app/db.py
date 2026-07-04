"""Асинхронний SQLAlchemy engine та сесії."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncSession:
    """FastAPI-залежність: віддає сесію на час запиту."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Створює таблиці, якщо їх немає (ідемпотентно). Міграції — через Alembic за потреби."""
    from . import models  # noqa: F401 — реєстрація моделей у метаданих

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
