"""Точка входу: FastAPI, роути, collector, віддача SPA-статики."""

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .collector import run_collector
from .config import LOG_LEVEL, PORT, check_secrets
from .db import SessionLocal, init_models
from .models import RedisServerConfig
from .redis_util import build_server_from_config
from .routes import auth, devices, events, geo, inventory, overview, servers, stream, users, webauthn
from .seed import seed_admin, seed_redis_configs
from sqlalchemy import select

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s : %(message)s")
logger = logging.getLogger("admin_panel")

STATIC_DIR = Path(os.environ.get("STATIC_DIR", "/app/static"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    check_secrets()
    await init_models()
    await seed_admin()
    await seed_redis_configs()
    async with SessionLocal() as s:
        result = await s.execute(
            select(RedisServerConfig).where(RedisServerConfig.enabled.is_(True)).order_by(RedisServerConfig.id)
        )
        app.state.redis_servers = [build_server_from_config(cfg) for cfg in result.scalars().all()]
    stop_event = asyncio.Event()
    app.state.stop_event = stop_event
    app.state.redis_servers_lock = asyncio.Lock()
    app.state.collector_task = asyncio.create_task(run_collector(app.state.redis_servers, stop_event))
    logger.info("Адмін-панель запущена на порту %s", PORT)
    try:
        yield
    finally:
        stop_event.set()
        app.state.collector_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await app.state.collector_task
        for server in app.state.redis_servers:
            await server.client.close()


app = FastAPI(title="JAAM Admin Panel", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(webauthn.router)
app.include_router(overview.router)
app.include_router(devices.router)
app.include_router(events.router)
app.include_router(inventory.router)
app.include_router(geo.router)
app.include_router(servers.router)
app.include_router(stream.router)
app.include_router(users.router)


@app.get("/api/health")
async def health():
    return {"ok": True}


# --- Віддача зібраного React SPA ---
if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    _static_root = STATIC_DIR.resolve()

    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = (_static_root / full_path).resolve()
        if full_path and candidate.is_relative_to(_static_root) and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_static_root / "index.html")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips=["*"])
