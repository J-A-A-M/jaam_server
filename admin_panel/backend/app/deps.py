"""Залежності FastAPI: поточний користувач із JWT-cookie."""

from fastapi import Depends, HTTPException, Request, status

from .config import COOKIE_NAME
from .security import decode_token


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Не авторизовано")
    return {"username": payload.get("sub"), "role": payload.get("role", "viewer")}


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Потрібні права адміністратора")
    return user


CurrentUser = Depends(get_current_user)
