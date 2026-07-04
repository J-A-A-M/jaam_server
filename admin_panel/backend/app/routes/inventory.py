"""Реєстр офіційних JAAM-мап (jaam_maps): CRUD, bulk-імпорт, склейка зі станом онлайн."""

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import Device, JaamMap
from ..schemas import BulkResult, JaamMapIn, JaamMapListOut, JaamMapOut

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _to_out(m: JaamMap, device: Device | None) -> JaamMapOut:
    out = JaamMapOut.model_validate(m)
    if device is not None:
        out.ever_seen = True
        out.is_online = device.is_online
        last_seen = device.last_seen
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
        out.last_seen = last_seen
        out.firmware = device.firmware
    return out


@router.get("", response_model=JaamMapListOut)
async def list_maps(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="Пошук за chip_id / order / customer_info"),
    status_: str | None = Query(None, alias="status", description="online|offline|never"),
    is_prototype: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(
            or_(JaamMap.chip_id.ilike(like), JaamMap.order_number.ilike(like), JaamMap.customer_info.ilike(like))
        )
    if is_prototype is not None:
        filters.append(JaamMap.is_prototype.is_(is_prototype))

    total = await session.scalar(select(func.count()).select_from(JaamMap).where(*filters))
    result = await session.execute(
        select(JaamMap)
        .where(*filters)
        .order_by(JaamMap.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    maps = result.scalars().all()

    chip_ids = [m.chip_id for m in maps]
    devices: dict[str, Device] = {}
    if chip_ids:
        dev_res = await session.execute(select(Device).where(Device.chip_id.in_(chip_ids)))
        devices = {d.chip_id: d for d in dev_res.scalars().all()}

    items = [_to_out(m, devices.get(m.chip_id)) for m in maps]
    # Фільтр за статусом онлайну застосовуємо після склейки
    if status_ == "online":
        items = [i for i in items if i.is_online]
    elif status_ == "offline":
        items = [i for i in items if i.ever_seen and not i.is_online]
    elif status_ == "never":
        items = [i for i in items if not i.ever_seen]

    return JaamMapListOut(total=total or 0, page=page, page_size=page_size, items=items)


@router.post("", response_model=JaamMapOut, status_code=201)
async def create_map(
    body: JaamMapIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    chip_id = body.chip_id.strip()
    if not chip_id:
        raise HTTPException(status_code=400, detail="chip_id обов'язковий")
    if await session.get(JaamMap, chip_id):
        raise HTTPException(status_code=409, detail="Мапа з таким chip_id вже є в реєстрі")

    m = JaamMap(
        chip_id=chip_id,
        hw_version=body.hw_version,
        is_prototype=body.is_prototype,
        order_number=body.order_number,
        customer_info=body.customer_info,
    )
    session.add(m)
    await session.commit()
    await session.refresh(m)
    device = await session.get(Device, chip_id)
    return _to_out(m, device)


@router.put("/{chip_id}", response_model=JaamMapOut)
async def update_map(
    chip_id: str,
    body: JaamMapIn,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    m.hw_version = body.hw_version
    m.is_prototype = body.is_prototype
    m.order_number = body.order_number
    m.customer_info = body.customer_info
    await session.commit()
    await session.refresh(m)
    device = await session.get(Device, chip_id)
    return _to_out(m, device)


@router.delete("/{chip_id}", status_code=204)
async def delete_map(
    chip_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    await session.delete(m)
    await session.commit()


@router.post("/bulk", response_model=BulkResult)
async def bulk_upsert(
    body: list[JaamMapIn],
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Одноразовий імпорт із Google-таблиці: upsert за chip_id."""
    created = updated = 0
    for row in body:
        chip_id = row.chip_id.strip()
        if not chip_id:
            continue
        m = await session.get(JaamMap, chip_id)
        if m:
            m.hw_version = row.hw_version
            m.is_prototype = row.is_prototype
            m.order_number = row.order_number
            m.customer_info = row.customer_info
            updated += 1
        else:
            session.add(
                JaamMap(
                    chip_id=chip_id,
                    hw_version=row.hw_version,
                    is_prototype=row.is_prototype,
                    order_number=row.order_number,
                    customer_info=row.customer_info,
                )
            )
            created += 1
    await session.commit()
    return BulkResult(created=created, updated=updated, total=created + updated)
