"""Точки для карти: мапи з відомими координатами."""

import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import outerjoin, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import Device, JaamMap
from ..schemas import GeoPoint

router = APIRouter(prefix="/api/geo", tags=["geo"])


@router.get("", response_model=list[GeoPoint])
async def geo_points(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    status_: str | None = Query(None, alias="status", description="online|offline"),
    type_: str | None = Query(None, alias="type", description="jaam|self"),
):
    filters = [Device.lat.is_not(None), Device.lon.is_not(None)]
    if status_ == "online":
        filters.append(Device.is_online.is_(True))
    elif status_ == "offline":
        filters.append(Device.is_online.is_(False))
    if type_ == "jaam":
        filters.append(JaamMap.chip_id.is_not(None))
    elif type_ == "self":
        filters.append(JaamMap.chip_id.is_(None))

    # PII клієнтів (order_number, customer_info) — лише для адміністраторів.
    is_admin = user.get("role") == "admin"

    j = outerjoin(Device, JaamMap, Device.chip_id == JaamMap.chip_id)
    result = await session.execute(select(Device, JaamMap).select_from(j).where(*filters))
    points = []
    for d, reg in result.all():
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
                is_jaam=reg is not None,
                map_id=reg.map_id if reg else None,
                hw_version=reg.hw_version if reg else None,
                is_prototype=reg.is_prototype if reg else False,
                order_number=(reg.order_number if reg else None) if is_admin else None,
                customer_info=(reg.customer_info if reg else None) if is_admin else None,
            )
        )
    return points
