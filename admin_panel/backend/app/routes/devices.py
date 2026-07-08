"""Список мап (фільтр/пошук/сортування/пагінація) та деталі."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user
from ..models import Device, DeviceEvent, DeviceSession, JaamMap
from ..schemas import DeviceDetailOut, DeviceListOut, DeviceOut, EventOut, SessionOut

router = APIRouter(prefix="/api/devices", tags=["devices"])


def _device_out(d: Device, reg: JaamMap | None, include_pii: bool = True) -> DeviceOut:
    out = DeviceOut.model_validate(d)
    if reg is not None:
        out.is_jaam = True
        out.map_id = reg.map_id
        out.hw_version = reg.hw_version
        out.is_prototype = reg.is_prototype
        # PII клієнтів — лише для адміністраторів
        out.order_number = reg.order_number if include_pii else None
        out.customer_info = reg.customer_info if include_pii else None
    return out


_hw_version_subq = (
    select(JaamMap.hw_version).where(JaamMap.chip_id == Device.chip_id).correlate(Device).scalar_subquery()
)

_SORT_COLUMNS = {
    "last_seen": Device.last_seen,
    "first_seen": Device.first_seen,
    "chip_id": Device.chip_id,
    "firmware": Device.firmware,
    "region": Device.region,
    "country": Device.country,
    "is_online": Device.is_online,
    "hw_type": Device.hw_type,
    "hw_version": _hw_version_subq,
    "last_server": Device.last_server,
}

_SESSIONS_PAGE_SIZE = 20
_EVENTS_PAGE_SIZE = 20


@router.get("", response_model=DeviceListOut)
async def list_devices(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(None, description="Пошук за chip_id / firmware_id / city"),
    status_: str | None = Query(None, alias="status", description="online|offline"),
    firmware: str | None = None,
    hw: str | None = None,
    region: str | None = None,
    country: str | None = None,
    server: str | None = None,
    type_: str | None = Query(None, alias="type", description="jaam|self — офіційна JAAM чи самозбірка"),
    sort: str = "last_seen",
    order: str = "desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                Device.chip_id.ilike(like),
                Device.firmware_id.ilike(like),
                Device.firmware.ilike(like),
                Device.city.ilike(like),
                Device.last_ip.ilike(like),
            )
        )
    if status_ == "online":
        filters.append(Device.is_online.is_(True))
    elif status_ == "offline":
        filters.append(Device.is_online.is_(False))
    if firmware:
        filters.append(Device.firmware == firmware)
    if hw:
        filters.append(Device.hw_type == hw)
    if region:
        filters.append(Device.region == region)
    if country:
        filters.append(Device.country == country)
    if server:
        filters.append(Device.last_server == server)
    if type_ == "jaam":
        filters.append(Device.chip_id.in_(select(JaamMap.chip_id)))
    elif type_ == "self":
        filters.append(Device.chip_id.not_in(select(JaamMap.chip_id)))

    total = await session.scalar(select(func.count()).select_from(Device).where(*filters))

    sort_col = _SORT_COLUMNS.get(sort, Device.last_seen)
    sort_col = sort_col.desc() if order == "desc" else sort_col.asc()

    result = await session.execute(
        select(Device).where(*filters).order_by(sort_col).offset((page - 1) * page_size).limit(page_size)
    )
    devices = result.scalars().all()

    # Склейка з реєстром JAAM
    chip_ids = [d.chip_id for d in devices]
    registry: dict[str, JaamMap] = {}
    if chip_ids:
        reg_res = await session.execute(select(JaamMap).where(JaamMap.chip_id.in_(chip_ids)))
        registry = {m.chip_id: m for m in reg_res.scalars().all()}

    is_admin = user.get("role") == "admin"
    items = [_device_out(d, registry.get(d.chip_id), is_admin) for d in devices]
    return DeviceListOut(total=total or 0, page=page, page_size=page_size, items=items)


@router.get("/{chip_id}/same-ip", response_model=list[DeviceOut])
async def same_ip_devices(
    chip_id: str,
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    device = await session.get(Device, chip_id)
    if not device or not device.last_ip:
        return []

    result = await session.execute(
        select(Device)
        .where(Device.last_ip == device.last_ip, Device.chip_id != chip_id)
        .order_by(Device.is_online.desc(), Device.last_seen.desc())
    )
    devices = result.scalars().all()
    if not devices:
        return []

    chip_ids = [d.chip_id for d in devices]
    reg_res = await session.execute(select(JaamMap).where(JaamMap.chip_id.in_(chip_ids)))
    registry = {m.chip_id: m for m in reg_res.scalars().all()}

    is_admin = user.get("role") == "admin"
    return [_device_out(d, registry.get(d.chip_id), is_admin) for d in devices]


@router.get("/{chip_id}", response_model=DeviceDetailOut)
async def device_detail(
    chip_id: str,
    sessions_page: int = Query(1, ge=1),
    events_page: int = Query(1, ge=1),
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    import datetime

    is_admin = user.get("role") == "admin"
    device = await session.get(Device, chip_id)
    reg = await session.get(JaamMap, chip_id)

    if not device:
        if reg is None:
            raise HTTPException(status_code=404, detail="Мапу не знайдено")
        # Мапа є в реєстрі, але ще жодного разу не виходила онлайн
        stub = DeviceOut(
            chip_id=reg.chip_id,
            firmware=None,
            firmware_id=None,
            hw_type=None,
            is_online=False,
            first_seen=reg.created_at,
            last_seen=reg.created_at,
            last_online_at=None,
            connect_time=None,
            last_ip=None,
            city=None,
            region=None,
            country=None,
            org=None,
            location=None,
            lat=None,
            lon=None,
            latency=None,
            secure_connection=None,
            last_server=None,
            is_jaam=True,
            ever_seen=False,
            map_id=reg.map_id,
            hw_version=reg.hw_version,
            is_prototype=reg.is_prototype,
            order_number=reg.order_number if is_admin else None,
            customer_info=reg.customer_info if is_admin else None,
        )
        return DeviceDetailOut(device=stub, sessions=[], events=[])

    sessions_total = await session.scalar(
        select(func.count()).select_from(DeviceSession).where(DeviceSession.chip_id == chip_id)
    )
    sessions_res = await session.execute(
        select(DeviceSession)
        .where(DeviceSession.chip_id == chip_id)
        .order_by(DeviceSession.started_at.desc())
        .offset((sessions_page - 1) * _SESSIONS_PAGE_SIZE)
        .limit(_SESSIONS_PAGE_SIZE)
    )
    events_total = await session.scalar(
        select(func.count()).select_from(DeviceEvent).where(DeviceEvent.chip_id == chip_id)
    )
    events_res = await session.execute(
        select(DeviceEvent)
        .where(DeviceEvent.chip_id == chip_id)
        .order_by(DeviceEvent.ts.desc())
        .offset((events_page - 1) * _EVENTS_PAGE_SIZE)
        .limit(_EVENTS_PAGE_SIZE)
    )
    return DeviceDetailOut(
        device=_device_out(device, reg, is_admin),
        sessions=[SessionOut.model_validate(s) for s in sessions_res.scalars().all()],
        sessions_total=sessions_total or 0,
        events=[EventOut.model_validate(e) for e in events_res.scalars().all()],
        events_total=events_total or 0,
    )
