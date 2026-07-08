"""Авторизація: логін/логаут (JWT у httpOnly cookie), поточний користувач."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import COOKIE_NAME, COOKIE_SECURE, JWT_TTL_SECONDS
from ..db import get_session
from ..deps import get_current_user
from ..models import User
from ..ratelimit import register_failure, reset, retry_after
from ..schemas import LoginRequest, UserOut
from ..security import create_token, decode_token, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
):
    rl_key = request.client.host if request.client else "?"
    wait = retry_after(rl_key)
    if wait:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Забагато спроб входу. Спробуйте через {wait} с.",
            headers={"Retry-After": str(wait)},
        )

    result = await session.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        register_failure(rl_key)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Невірний логін або пароль")

    reset(rl_key)
    token = create_token(user.username, user.role, user.token_version)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=JWT_TTL_SECONDS,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="lax",
    )
    return UserOut(username=user.username, role=user.role)


@router.post("/logout")
async def logout(request: Request, response: Response, session: AsyncSession = Depends(get_session)):
    # Серверний logout: інкрементуємо token_version, щоб відкликати виданий токен
    # (а не лише стерти cookie на клієнті).
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_token(token) if token else None
    if payload and payload.get("sub"):
        user = await session.scalar(select(User).where(User.username == payload["sub"]))
        if user is not None:
            user.token_version += 1
            await session.commit()
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user: dict = Depends(get_current_user)):
    return UserOut(username=user["username"], role=user["role"])
