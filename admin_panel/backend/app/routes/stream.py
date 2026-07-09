"""SSE: живий потік лічильника онлайну та останніх подій."""

import asyncio
import datetime
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select
from starlette.responses import StreamingResponse

from ..config import COOKIE_NAME
from ..db import SessionLocal
from ..models import Device, DeviceEvent, User
from ..security import decode_token

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger(__name__)

STREAM_INTERVAL = 5


async def _snapshot(session) -> dict:
    """Fetch dashboard snapshot using existing session (no new connection per snapshot)."""
    online = await session.scalar(select(func.count()).select_from(Device).where(Device.is_online.is_(True)))
    total = await session.scalar(select(func.count()).select_from(Device))
    events_res = await session.execute(select(DeviceEvent).order_by(DeviceEvent.ts.desc()).limit(15))
    events = [
        {
            "chip_id": e.chip_id,
            "type": e.type,
            "ts": (e.ts.replace(tzinfo=datetime.timezone.utc) if e.ts.tzinfo is None else e.ts).isoformat(),
            "details": e.details,
        }
        for e in events_res.scalars().all()
    ]
    return {"online_now": online or 0, "total_registered": total or 0, "events": events}


async def _token_still_valid(session, token: str | None) -> bool:
    """Звіряє токен із БД (існування користувача + token_version), як get_current_user."""
    payload = decode_token(token) if token else None
    if not payload or not payload.get("sub"):
        return False
    user = await session.scalar(select(User).where(User.username == payload["sub"]))
    return user is not None and payload.get("tv", 0) == user.token_version


@router.get("")
async def stream(request: Request):
    # Авторизація вручну (SSE зручніше перевіряти напряму)
    token = request.cookies.get(COOKIE_NAME)
    async with SessionLocal() as session:
        if not await _token_still_valid(session, token):
            raise HTTPException(status_code=401, detail="Не авторизовано")

    async def event_gen():
        while True:
            if await request.is_disconnected():
                break
            try:
                # Коротка сесія на кожен знімок: з'єднання повертається в пул між
                # знімками, транзакція не висить відкритою (idle in transaction).
                async with SessionLocal() as session:
                    if not await _token_still_valid(session, token):
                        break  # токен відкликано або користувача видалено
                    data = await _snapshot(session)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            except Exception:
                logger.exception("SSE snapshot failed")
            await asyncio.sleep(STREAM_INTERVAL)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
