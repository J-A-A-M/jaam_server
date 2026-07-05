"""Асинхронний SQLAlchemy engine та сесії."""

from sqlalchemy import text
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


_MIGRATIONS = text(
    """
DO $$
BEGIN
    -- devices: custom_id → firmware_id
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_name='devices' AND column_name='custom_id')
    AND NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_name='devices' AND column_name='firmware_id') THEN
        ALTER TABLE devices RENAME COLUMN custom_id TO firmware_id;
    ELSIF EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name='devices' AND column_name='custom_id') THEN
        UPDATE devices SET firmware_id = custom_id WHERE firmware_id IS NULL;
        ALTER TABLE devices DROP COLUMN custom_id;
    END IF;

    -- device_sessions: add firmware_id if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='device_sessions' AND column_name='firmware_id') THEN
        ALTER TABLE device_sessions ADD COLUMN firmware_id VARCHAR(128);
    END IF;

    -- Strip firmware id-suffix from existing devices rows
    UPDATE devices
    SET firmware_id = COALESCE(firmware_id,
                               substring(firmware FROM position('_' IN firmware) + 1)),
        firmware    = substring(firmware FROM 1 FOR position('_' IN firmware) - 1)
    WHERE firmware IS NOT NULL AND position('_' IN firmware) > 0;

    -- Strip firmware id-suffix from existing session rows
    UPDATE device_sessions
    SET firmware_id = CASE WHEN position('_' IN firmware) > 0
                           THEN substring(firmware FROM position('_' IN firmware) + 1)
                           ELSE NULL END,
        firmware    = CASE WHEN position('_' IN firmware) > 0
                           THEN substring(firmware FROM 1 FOR position('_' IN firmware) - 1)
                           ELSE firmware END
    WHERE firmware IS NOT NULL AND position('_' IN firmware) > 0;

    -- Backfill hw_type from firmware name for devices that have no hw_type yet
    UPDATE devices
    SET hw_type = CASE
        WHEN lower(firmware) LIKE '%c3%' THEN 'ESP32-C3'
        WHEN lower(firmware) LIKE '%s3%' THEN 'ESP32-S3'
        ELSE 'ESP32'
    END
    WHERE firmware IS NOT NULL AND hw_type IS NULL;

    -- jaam_maps: add map_id column if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                  WHERE table_name='jaam_maps' AND column_name='map_id') THEN
        ALTER TABLE jaam_maps ADD COLUMN map_id VARCHAR(128);
    END IF;
END $$;
"""
)


async def init_models() -> None:
    """Створює таблиці, якщо їх немає, і запускає ідемпотентні міграції."""
    from . import models  # noqa: F401 — реєстрація моделей у метаданих

    async with engine.begin() as conn:
        await conn.execute(_MIGRATIONS)
        await conn.run_sync(Base.metadata.create_all)
