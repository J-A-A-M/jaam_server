"""Налаштування панелі, що редагуються через UI (наразі — список hw_version)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user, require_admin
from ..models import HardwareVersion
from ..schemas import HardwareVersionIn, HardwareVersionOut

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/hw-versions", response_model=list[HardwareVersionOut])
async def list_hw_versions(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(
        select(HardwareVersion).order_by(HardwareVersion.sort_order)
    )
    return [HardwareVersionOut.model_validate(v) for v in result.scalars().all()]


@router.post("/hw-versions", response_model=HardwareVersionOut, status_code=201)
async def create_hw_version(
    body: HardwareVersionIn,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Назва не може бути порожньою")
    exists = await session.scalar(
        select(HardwareVersion).where(HardwareVersion.name == name)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Таке значення вже є в списку")
    max_order = await session.scalar(
        select(HardwareVersion.sort_order).order_by(HardwareVersion.sort_order.desc())
    )
    version = HardwareVersion(name=name, sort_order=(max_order or 0) + 1)
    session.add(version)
    await session.commit()
    await session.refresh(version)
    return HardwareVersionOut.model_validate(version)


@router.delete("/hw-versions/{version_id}", status_code=204)
async def delete_hw_version(
    version_id: int,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    version = await session.get(HardwareVersion, version_id)
    if not version:
        raise HTTPException(status_code=404, detail="Значення не знайдено")
    await session.delete(version)
    await session.commit()


@router.post("/hw-versions/reorder", response_model=list[HardwareVersionOut])
async def reorder_hw_versions(
    ordered_ids: list[int],
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(HardwareVersion))
    by_id = {v.id: v for v in result.scalars().all()}
    if set(ordered_ids) != set(by_id):
        raise HTTPException(
            status_code=400, detail="Список id не відповідає наявним значенням"
        )
    for idx, vid in enumerate(ordered_ids):
        by_id[vid].sort_order = idx
    await session.commit()
    return [HardwareVersionOut.model_validate(by_id[vid]) for vid in ordered_ids]
