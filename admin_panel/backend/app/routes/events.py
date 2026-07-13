"""Глобальна стрічка подій з пагінацією, пошуком, сортуванням та фільтрацією."""

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import DEFAULT_SERVER_TZ
from ..db import get_session
from ..deps import get_current_user
from ..models import Device, DeviceEvent, JaamMap
from ..schemas import EventListOut, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])

_SORT_COLUMNS = {
    "ts": DeviceEvent.ts,
    "type": DeviceEvent.type,
    "chip_id": DeviceEvent.chip_id,
}

try:
    from zoneinfo import ZoneInfo

    _SERVER_ZONE = ZoneInfo(DEFAULT_SERVER_TZ)
except Exception:
    _SERVER_ZONE = datetime.timezone.utc


@router.get("", response_model=EventListOut)
async def list_events(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="Пошук за chip_id або деталями"),
    type_: str | None = Query(None, alias="type", description="Фільтр за типом події"),
    period: str | None = Query(None, description="today|week|month"),
    sort: str = "ts",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    filters = []

    if q:
        like = f"%{q}%"
        filters.append(or_(DeviceEvent.chip_id.ilike(like), DeviceEvent.details.ilike(like)))

    if type_:
        filters.append(DeviceEvent.type == type_)

    if period:
        now = datetime.datetime.now(_SERVER_ZONE)
        if period == "today":
            start = datetime.datetime.combine(now.date(), datetime.time.min, tzinfo=_SERVER_ZONE)
        elif period == "week":
            start = now - datetime.timedelta(days=7)
        elif period == "month":
            start = now - datetime.timedelta(days=30)
        else:
            start = None
        if start:
            filters.append(DeviceEvent.ts >= start)

    sort_col = _SORT_COLUMNS.get(sort, DeviceEvent.ts)
    sort_expr = desc(sort_col).nulls_last() if order == "desc" else asc(sort_col).nulls_last()

    total = await session.scalar(select(func.count()).select_from(DeviceEvent).where(*filters))
    result = await session.execute(
        select(DeviceEvent).where(*filters).order_by(sort_expr).offset((page - 1) * page_size).limit(page_size)
    )
    events = result.scalars().all()

    # Склейка з devices/реєстром JAAM — для підпису під chip_id та чипа типу мапи
    chip_ids = {e.chip_id for e in events if e.chip_id}
    firmware_ids: dict[str, str | None] = {}
    registry: dict[str, JaamMap] = {}
    if chip_ids:
        dev_res = await session.execute(select(Device.chip_id, Device.firmware_id).where(Device.chip_id.in_(chip_ids)))
        firmware_ids = dict(dev_res.all())
        reg_res = await session.execute(select(JaamMap).where(JaamMap.chip_id.in_(chip_ids)))
        registry = {m.chip_id: m for m in reg_res.scalars().all()}

    items = []
    for e in events:
        out = EventOut.model_validate(e)
        if e.chip_id:
            out.firmware_id = firmware_ids.get(e.chip_id)
            reg = registry.get(e.chip_id)
            if reg is not None:
                out.is_jaam = True
                out.hw_version = reg.hw_version
                out.is_prototype = reg.is_prototype
        items.append(out)
    return EventListOut(total=total or 0, page=page, page_size=page_size, items=items)
