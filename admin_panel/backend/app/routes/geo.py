"""Точки для карти: мапи з відомими координатами."""

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import Device
from ..schemas import GeoPoint

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("", response_model=list[GeoPoint])
async def geo_points(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    status_: str | None = Query(None, alias="status", description="online|offline"),
):
    filters = [Device.lat.is_not(None), Device.lon.is_not(None)]
    if status_ == "online":
        filters.append(Device.is_online.is_(True))
    elif status_ == "offline":
        filters.append(Device.is_online.is_(False))

    result = await session.execute(select(Device).where(*filters))
    points = []
    for d in result.scalars().all():
        last_seen = d.last_seen
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
        points.append(
            GeoPoint(
                chip_id=d.chip_id,
                lat=d.lat,
                lon=d.lon,
                is_online=d.is_online,
                firmware=d.firmware,
                city=d.city,
                region=d.region,
                org=d.org,
                last_seen=last_seen,
            )
        )
    return points
