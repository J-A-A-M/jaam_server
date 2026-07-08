"""Керування користувачами панелі (лише для ролі admin) та зміна власного пароля."""

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import COOKIE_NAME, COOKIE_SECURE, JWT_TTL_SECONDS
from ..db import get_session
from ..deps import get_current_user, require_admin
from ..models import User
from ..schemas import PasswordChange, UserCreate, UserListItem, UserUpdate
from ..security import create_token, hash_password, verify_password

router = APIRouter(prefix="/api/users", tags=["users"])

_MIN_PASSWORD_LEN = 8


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


@router.post("/me/password", status_code=204)
async def change_own_password(
    body: PasswordChange,
    response: Response,
    current: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if len(body.new_password) < _MIN_PASSWORD_LEN:
        raise HTTPException(status_code=400, detail=f"Пароль має бути не коротшим за {_MIN_PASSWORD_LEN} символів")
    user = await session.scalar(select(User).where(User.username == current["username"]))
    if user is None:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Невірний поточний пароль")

    user.password_hash = hash_password(body.new_password)
    # Відкликаємо всі інші сесії; поточній видаємо свіжий cookie з новим token_version
    user.token_version += 1
    await session.commit()

    token = create_token(user.username, user.role, user.token_version)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )


@router.put("/{username}", response_model=UserListItem)
async def update_user(
    username: str,
    body: UserUpdate,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    # Блокуємо рядки, щоб перевірка "останній адмін" була консистентною при конкурентних змінах
    result = await session.execute(select(User).with_for_update())
    all_users = result.scalars().all()
    user = next((u for u in all_users if u.username == username), None)
    if not user:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if body.role is not None:
        if body.role not in ("admin", "viewer"):
            raise HTTPException(status_code=400, detail="Роль має бути admin або viewer")
        admin_count = sum(1 for u in all_users if u.role == "admin")
        if user.role == "admin" and body.role != "admin" and admin_count <= 1:
            raise HTTPException(status_code=400, detail="Не можна знизити роль останнього адміністратора")
        if user.role != body.role:
            user.role = body.role
            user.token_version += 1  # застосувати нову роль до всіх активних токенів користувача

    if body.password is not None:
        if len(body.password) < _MIN_PASSWORD_LEN:
            raise HTTPException(status_code=400, detail=f"Пароль має бути не коротшим за {_MIN_PASSWORD_LEN} символів")
        user.password_hash = hash_password(body.password)
        user.token_version += 1  # відкликати сесії після скидання пароля адміністратором

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
