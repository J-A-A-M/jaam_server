"""Глобальна стрічка подій з пагінацією (для дашборду)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import DeviceEvent
from ..schemas import EventListOut, EventOut

router = APIRouter(prefix="/api/events", tags=["events"])


@router.get("", response_model=EventListOut)
async def list_events(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    total = await session.scalar(select(func.count()).select_from(DeviceEvent))
    result = await session.execute(
        select(DeviceEvent).order_by(DeviceEvent.ts.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [EventOut.model_validate(e) for e in result.scalars().all()]
    return EventListOut(total=total or 0, page=page, page_size=page_size, items=items)
