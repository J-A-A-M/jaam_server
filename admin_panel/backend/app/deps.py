"""Залежності FastAPI: поточний користувач із JWT-cookie."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import COOKIE_NAME
from .db import get_session
from .models import User
from .security import decode_token

_UNAUTHORIZED = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизовано")


async def get_current_user(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload:
        raise _UNAUTHORIZED

    username = payload.get("sub")
    if not username:
        raise _UNAUTHORIZED

    # Звіряємо токен із поточним станом користувача в БД: видалений користувач,
    # змінена роль чи відкликаний токен (token_version) більше не проходять.
    user = await session.scalar(select(User).where(User.username == username))
    if user is None or payload.get("tv", 0) != user.token_version:
        raise _UNAUTHORIZED

    return {"username": user.username, "role": user.role}


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Потрібні права адміністратора",
        )
    return user


CurrentUser = Depends(get_current_user)
