"""Керування користувачами панелі (лише для ролі admin)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import require_admin
from ..models import User
from ..schemas import UserCreate, UserListItem
from ..security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserListItem])
async def list_users(
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(User).order_by(User.created_at.asc()))
    return [UserListItem.model_validate(u) for u in result.scalars().all()]


@router.post("", response_model=UserListItem, status_code=201)
async def create_user(
    body: UserCreate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    username = body.username.strip()
    if not username or not body.password:
        raise HTTPException(status_code=400, detail="Логін і пароль обов'язкові")
    if body.role not in ("admin", "viewer"):
        raise HTTPException(status_code=400, detail="Роль має бути admin або viewer")
    exists = await session.scalar(select(User).where(User.username == username))
    if exists:
        raise HTTPException(status_code=409, detail="Користувач із таким логіном вже є")

    user = User(username=username, password_hash=hash_password(body.password), role=body.role)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserListItem.model_validate(user)


@router.delete("/{username}", status_code=204)
async def delete_user(
    username: str,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    # Lock all user rows so concurrent deletes can't bypass the checks
    result = await session.execute(select(User).with_for_update())
    all_users = result.scalars().all()
    user = next((u for u in all_users if u.username == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    # Не дозволяти видаляти себе
    if admin["username"] == username:
        raise HTTPException(status_code=400, detail="Не можна видалити власний акаунт")

    # Гарантувати ≥1 admin завжди
    admin_count = sum(1 for u in all_users if u.role == "admin")
    if user.role == "admin" and admin_count <= 1:
        raise HTTPException(status_code=400, detail="Не можна видалити останнього адміністратора")

    await session.delete(user)
    await session.commit()
