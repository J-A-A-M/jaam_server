"""Сідання адміністратора та Redis-конфігів при першому запуску."""

import logging

from sqlalchemy import func, select

from .config import ADMIN_PASSWORD, ADMIN_USER, parse_redis_hosts, redis_name
from .db import SessionLocal
from .models import HardwareVersion, RedisServerConfig, User
from .security import hash_password

logger = logging.getLogger("admin_panel.seed")

_DEFAULT_HW_VERSIONS = [
    "JAAM3.3",
    "JAAM3.2",
    "JAAM3.1",
    "JAAM3.0",
    "JAAM2",
    "JAAM1",
    "NOT JAAM",
]


async def seed_hw_versions() -> None:
    """Ініціалізує hardware_versions стандартним списком, якщо таблиця порожня."""
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(HardwareVersion))
        if count:
            return
        for idx, name in enumerate(_DEFAULT_HW_VERSIONS):
            session.add(HardwareVersion(name=name, sort_order=idx))
        await session.commit()
        logger.info("Список hw_version ініціалізовано стандартними значеннями")


async def seed_redis_configs() -> None:
    """Ініціалізує redis_server_configs з env-змінних, якщо таблиця порожня."""
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count()).select_from(RedisServerConfig)
        )
        if count:
            return
        for idx, cfg in enumerate(parse_redis_hosts()):
            session.add(
                RedisServerConfig(
                    name=redis_name(cfg, idx),
                    host=cfg.get("host", "redis"),
                    port=int(cfg.get("port", 6379)),
                    db=int(cfg.get("db", 0)),
                    password=cfg.get("password") or None,
                    enabled=True,
                )
            )
        await session.commit()
        logger.info("Redis-конфіги ініціалізовано з env-змінних")


async def seed_admin() -> None:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        if count:
            return
        session.add(
            User(
                username=ADMIN_USER,
                password_hash=hash_password(ADMIN_PASSWORD),
                role="admin",
            )
        )
        await session.commit()
        logger.warning(
            "Створено адміністратора '%s' (змініть пароль через ADMIN_PASSWORD)",
            ADMIN_USER,
        )
