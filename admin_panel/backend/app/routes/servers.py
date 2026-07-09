"""Стан Redis-серверів та управління конфігурацією (тільки admin)."""

import logging

import redis.asyncio as redis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_session
from ..deps import get_current_user, require_admin
from ..models import RedisServerConfig, utcnow
from ..redis_util import build_server_from_config, count_clients
from ..schemas import RedisServerConfigIn, RedisServerConfigOut, RedisServerConfigUpdate, ServerStatus

logger = logging.getLogger("admin_panel.servers")
router = APIRouter(prefix="/api/servers", tags=["servers"])


def _out(cfg: RedisServerConfig) -> RedisServerConfigOut:
    return RedisServerConfigOut(
        id=cfg.id,
        name=cfg.name,
        host=cfg.host,
        port=cfg.port,
        db=cfg.db,
        has_password=bool(cfg.password),
        enabled=cfg.enabled,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


async def _reload(request: Request, session: AsyncSession) -> None:
    """Оновлює app.state.redis_servers з БД без перезапуску collector-loop."""
    result = await session.execute(
        select(RedisServerConfig).where(RedisServerConfig.enabled.is_(True)).order_by(RedisServerConfig.id)
    )
    configs = result.scalars().all()
    old_servers = list(request.app.state.redis_servers)
    new_servers = [build_server_from_config(cfg) for cfg in configs]

    # Atomic replacement under lock to prevent race with collector
    async with request.app.state.redis_servers_lock:
        request.app.state.redis_servers.clear()
        request.app.state.redis_servers.extend(new_servers)

    for server in old_servers:
        try:
            await server.client.aclose()
        except Exception:
            logger.warning("Не вдалося закрити з'єднання Redis '%s'", server.name, exc_info=True)


# --- Статус (всі авторизовані користувачі) ---


@router.get("", response_model=list[ServerStatus])
async def servers_status(request: Request, user: dict = Depends(get_current_user)):
    now = utcnow()
    out: list[ServerStatus] = []
    for server in request.app.state.redis_servers:
        try:
            await server.client.ping()
            online = await count_clients(server.client)
            out.append(ServerStatus(name=server.name, ok=True, online=online, checked_at=now))
        except Exception:
            out.append(ServerStatus(name=server.name, ok=False, online=0, checked_at=now))
    return out


# --- CRUD конфігурацій (тільки admin) ---


@router.get("/config", response_model=list[RedisServerConfigOut])
async def list_configs(
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.execute(select(RedisServerConfig).order_by(RedisServerConfig.id))
    return [_out(cfg) for cfg in result.scalars().all()]


@router.post("/config", response_model=RedisServerConfigOut, status_code=201)
async def create_config(
    body: RedisServerConfigIn,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if not body.name.strip() or not body.host.strip():
        raise HTTPException(status_code=400, detail="Назва і хост обов'язкові")
    cfg = RedisServerConfig(
        name=body.name.strip(),
        host=body.host.strip(),
        port=body.port,
        db=body.db,
        password=body.password or None,
        enabled=body.enabled,
    )
    session.add(cfg)
    await session.commit()
    await session.refresh(cfg)
    await _reload(request, session)
    return _out(cfg)


@router.put("/config/{cfg_id}", response_model=RedisServerConfigOut)
async def update_config(
    cfg_id: int,
    body: RedisServerConfigUpdate,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    cfg = await session.get(RedisServerConfig, cfg_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Конфігурацію не знайдено")

    fields = body.model_fields_set
    if "name" in fields and body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Назва не може бути порожньою")
        cfg.name = name
    if "host" in fields and body.host is not None:
        host = body.host.strip()
        if not host:
            raise HTTPException(status_code=400, detail="Хост не може бути порожнім")
        cfg.host = host
    if "port" in fields and body.port is not None:
        cfg.port = body.port
    if "db" in fields and body.db is not None:
        cfg.db = body.db
    if "password" in fields:
        cfg.password = body.password or None  # "" → None (очистити)
    if "enabled" in fields and body.enabled is not None:
        cfg.enabled = body.enabled
    cfg.updated_at = utcnow()

    await session.commit()
    await session.refresh(cfg)
    await _reload(request, session)
    return _out(cfg)


@router.delete("/config/{cfg_id}", status_code=204)
async def delete_config(
    cfg_id: int,
    request: Request,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    cfg = await session.get(RedisServerConfig, cfg_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Конфігурацію не знайдено")
    await session.delete(cfg)
    await session.commit()
    await _reload(request, session)


@router.post("/config/{cfg_id}/test", response_model=ServerStatus)
async def test_config(
    cfg_id: int,
    admin: dict = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    cfg = await session.get(RedisServerConfig, cfg_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Конфігурацію не знайдено")
    now = utcnow()
    client = redis.Redis(
        host=cfg.host,
        port=cfg.port,
        db=cfg.db,
        password=cfg.password or None,
        decode_responses=True,
        socket_connect_timeout=5,
    )
    try:
        await client.ping()
        online = await count_clients(client)
        return ServerStatus(name=cfg.name, ok=True, online=online, checked_at=now)
    except Exception:
        return ServerStatus(name=cfg.name, ok=False, online=0, checked_at=now)
    finally:
        await client.aclose()
