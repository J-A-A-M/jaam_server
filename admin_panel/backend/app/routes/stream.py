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
from ..models import Device, DeviceEvent
from ..security import decode_token

router = APIRouter(prefix="/api/stream", tags=["stream"])
logger = logging.getLogger(__name__)

STREAM_INTERVAL = 5


async def _snapshot() -> dict:
    async with SessionLocal() as session:
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


@router.get("")
async def stream(request: Request):
    # Авторизація вручну (SSE зручніше перевіряти напряму)
    token = request.cookies.get(COOKIE_NAME)
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="Не авторизовано")

    async def event_gen():
        while True:
            if await request.is_disconnected():
                break
            try:
                data = await _snapshot()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
            except Exception:
                logger.exception("SSE snapshot failed")
            await asyncio.sleep(STREAM_INTERVAL)

    return StreamingResponse(event_gen(), media_type="text/event-stream")
