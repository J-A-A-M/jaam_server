"""Сідання адміністратора при першому запуску."""

import logging

from sqlalchemy import func, select

from .config import ADMIN_PASSWORD, ADMIN_USER
from .db import SessionLocal
from .models import User
from .security import hash_password

logger = logging.getLogger("admin_panel.seed")


async def seed_admin() -> None:
    async with SessionLocal() as session:
        count = await session.scalar(select(func.count()).select_from(User))
        if count:
            return
        session.add(User(username=ADMIN_USER, password_hash=hash_password(ADMIN_PASSWORD), role="admin"))
        await session.commit()
        logger.warning("Створено адміністратора '%s' (змініть пароль через ADMIN_PASSWORD)", ADMIN_USER)
