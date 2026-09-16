"""Реєстр офіційних JAAM-мап (jaam_maps): CRUD, склейка зі станом онлайн."""

import datetime
import hashlib
import secrets as pysecrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import Integer, case, cast, func, or_, outerjoin, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user, require_admin
from ..device_auth import derive_device_secret
from ..models import Device, JaamMap
from ..redis_util import mirror_claim_code, mirror_device_auth
from ..schemas import (
    ClaimCodeOut,
    JaamMapIn,
    JaamMapListOut,
    JaamMapOut,
    ProvisionOut,
    WhitelistIn,
)

# Без неоднозначних символів (0/O, 1/I) - код читають/диктують вголос кінцевому користувачу.
_CLAIM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CLAIM_CODE_LENGTH = 8
_CLAIM_CODE_TTL_S = 24 * 3600

router = APIRouter(prefix="/api/inventory", tags=["inventory"])

_order_num_sort = case(
    (JaamMap.order_number.op("~")(r"^\d+$"), cast(JaamMap.order_number, Integer)),
    else_=None,
)

_SORT_COLUMNS = {
    "chip_id": JaamMap.chip_id,
    "map_id": JaamMap.map_id,
    "hw_version": JaamMap.hw_version,
    "order_number": _order_num_sort,
    "customer_info": JaamMap.customer_info.collate("und-x-icu"),
    "is_prototype": JaamMap.is_prototype,
    "is_online": Device.is_online,
    "last_seen": Device.last_seen,
    "firmware": Device.firmware,
}


def _to_out(m: JaamMap, device: Device | None, include_pii: bool = True) -> JaamMapOut:
    out = JaamMapOut.model_validate(m)
    if not include_pii:
        # PII клієнтів — лише для адміністраторів
        out.order_number = None
        out.customer_info = None
    if device is not None:
        out.ever_seen = True
        out.is_online = device.is_online
        last_seen = device.last_seen
        if last_seen and last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=datetime.timezone.utc)
        out.last_seen = last_seen
        out.firmware = device.firmware
        out.firmware_id = device.firmware_id
    return out


@router.get("", response_model=JaamMapListOut)
async def list_maps(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    q: str | None = Query(
        None, description="Пошук за chip_id / map_id / order / customer_info"
    ),
    status_: str | None = Query(
        None, alias="status", description="online|offline|never"
    ),
    is_prototype: bool | None = None,
    sort: str = "chip_id",
    order: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    j = outerjoin(JaamMap, Device, JaamMap.chip_id == Device.chip_id)
    filters = []
    if q:
        like = f"%{q}%"
        filters.append(
            or_(
                JaamMap.chip_id.ilike(like),
                JaamMap.map_id.ilike(like),
                JaamMap.order_number.ilike(like),
                JaamMap.customer_info.ilike(like),
            )
        )
    if is_prototype is not None:
        filters.append(JaamMap.is_prototype.is_(is_prototype))
    if status_ == "online":
        filters.append(Device.is_online.is_(True))
    elif status_ == "offline":
        filters.append(Device.is_online.is_(False))
    elif status_ == "never":
        filters.append(Device.chip_id.is_(None))

    total = await session.scalar(
        select(func.count())
        .select_from(JaamMap)
        .outerjoin(Device, JaamMap.chip_id == Device.chip_id)
        .where(*filters)
    )

    sort_col = _SORT_COLUMNS.get(sort, JaamMap.chip_id)
    sort_expr = (
        sort_col.desc().nulls_last() if order == "desc" else sort_col.asc().nulls_last()
    )

    result = await session.execute(
        select(JaamMap, Device)
        .select_from(j)
        .where(*filters)
        .order_by(sort_expr)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    is_admin = user.get("role") == "admin"
    items = [_to_out(m, d, is_admin) for m, d in result.all()]
    return JaamMapListOut(total=total or 0, page=page, page_size=page_size, items=items)


@router.post("", response_model=JaamMapOut, status_code=201)
async def create_map(
    body: JaamMapIn,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    chip_id = body.chip_id.strip()
    if not chip_id:
        raise HTTPException(status_code=400, detail="chip_id обов'язковий")

    m = JaamMap(
        chip_id=chip_id,
        map_id=body.map_id,
        hw_version=body.hw_version,
        is_prototype=body.is_prototype,
        order_number=body.order_number,
        customer_info=body.customer_info,
    )
    try:
        session.add(m)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Мапа з таким chip_id вже є в реєстрі"
        )
    await session.refresh(m)
    device = await session.get(Device, chip_id)
    return _to_out(m, device)


@router.put("/{chip_id}", response_model=JaamMapOut)
async def update_map(
    chip_id: str,
    body: JaamMapIn,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    m.map_id = body.map_id
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
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")
    await session.delete(m)
    await session.commit()


@router.post("/{chip_id}/provision", response_model=ProvisionOut)
async def provision_secret(
    chip_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Видає (ротує) device-secret для jaam_touch: bump secret_version, whitelisted=True,
    дзеркалить {version, whitelisted} у Redis на всі сервери, повертає plaintext-секрет
    ОДИН раз — ніде на сервері не зберігається (секрет — похідний від chip_id+version).
    """
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    m.secret_version += 1
    m.whitelisted = True
    await session.commit()

    secret_hex = derive_device_secret(chip_id, m.secret_version).hex()
    await mirror_device_auth(
        request.app.state.redis_servers, chip_id, m.secret_version, m.whitelisted
    )

    return ProvisionOut(
        chip_id=chip_id,
        secret_hex=secret_hex,
        secret_version=m.secret_version,
        whitelisted=m.whitelisted,
    )


@router.post("/{chip_id}/claim-code", response_model=ClaimCodeOut)
async def issue_claim_code(
    chip_id: str,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Для кінцевого користувача, не техніка з серійним портом: ротує secret_version (як і
    /provision), але замість 64-символьного hex видає короткий одноразовий код (24г). Пристрій
    сам забирає похідний секрет через POST /touch/claim на update_server (chip_id+code) -
    жодного комп'ютера чи кабелю не потрібно, лише WiFi. Код ніде не зберігається у відкритому
    вигляді - лише SHA-256 хеш, мирориться в Redis (device_claim:<CHIP_ID>, TTL) тим самим
    шляхом, яким /provision мирориться device_auth."""
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    m.secret_version += 1
    m.whitelisted = True
    await session.commit()

    code = "".join(
        pysecrets.choice(_CLAIM_CODE_ALPHABET) for _ in range(_CLAIM_CODE_LENGTH)
    )
    code_hash = hashlib.sha256(code.encode()).hexdigest()

    await mirror_device_auth(
        request.app.state.redis_servers, chip_id, m.secret_version, m.whitelisted
    )
    await mirror_claim_code(
        request.app.state.redis_servers, chip_id, code_hash, _CLAIM_CODE_TTL_S
    )

    return ClaimCodeOut(
        chip_id=chip_id,
        claim_code=code,
        secret_version=m.secret_version,
        expires_in_s=_CLAIM_CODE_TTL_S,
    )


@router.patch("/{chip_id}/whitelist", response_model=JaamMapOut)
async def set_whitelisted(
    chip_id: str,
    body: WhitelistIn,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Вмикає/вимикає доступ пристрою без ротації секрету (напр. швидке відкликання
    вкраденого/повернутого пристрою)."""
    m = await session.get(JaamMap, chip_id)
    if not m:
        raise HTTPException(status_code=404, detail="Запис не знайдено")

    m.whitelisted = body.whitelisted
    await session.commit()
    await session.refresh(m)

    await mirror_device_auth(
        request.app.state.redis_servers, chip_id, m.secret_version, m.whitelisted
    )

    device = await session.get(Device, chip_id)
    return _to_out(m, device)
