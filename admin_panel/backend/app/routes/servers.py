"""Здоров'я Redis-серверів та кількість онлайн-клієнтів на кожному."""

from fastapi import APIRouter, Depends, Request

from ..deps import get_current_user
from ..models import utcnow
from ..redis_util import count_clients
from ..schemas import ServerStatus

router = APIRouter(prefix="/api/servers", tags=["servers"])


@router.get("", response_model=list[ServerStatus])
async def servers(request: Request, user: dict = Depends(get_current_user)):
    redis_servers = request.app.state.redis_servers
    out: list[ServerStatus] = []
    now = utcnow()
    for server in redis_servers:
        try:
            await server.client.ping()
            online = await count_clients(server.client)
            out.append(ServerStatus(name=server.name, ok=True, online=online, checked_at=now))
        except Exception:  # noqa: BLE001
            out.append(ServerStatus(name=server.name, ok=False, online=0, checked_at=now))
    return out
