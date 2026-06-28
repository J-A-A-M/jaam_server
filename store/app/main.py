"""Точка входу: збірка Starlette-застосунку магазину."""

import importlib
import logging

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles

from app.config import BASE_DIR, HOST, LOGGING, MEDIA_URL, PORT, SESSION_SECRET, UPLOAD_DIR
from app.db import init_db

logging.basicConfig(level=getattr(logging, LOGGING.upper(), logging.INFO))
log = logging.getLogger("store")

# Route-модулі. Кожен експортує `routes: list[Route]`.
# Адмін-модулі підвантажуються опціонально (можуть зʼявитись пізніше).
ROUTE_MODULES = [
    ("app.routes.storefront", True),
    ("app.routes.admin_system", False),
    ("app.routes.admin_catalog", False),
    ("app.routes.admin_orders", False),
    ("app.routes.admin_discounts", False),
    ("app.routes.admin_settings", False),
    ("app.routes.admin_stickers", False),
    ("app.routes.admin_product_discounts", False),
]


def collect_routes():
    routes = []
    for module_name, required in ROUTE_MODULES:
        try:
            module = importlib.import_module(module_name)
            routes.extend(module.routes)
            log.info("Підключено маршрути: %s (%d)", module_name, len(module.routes))
        except ImportError as e:
            if required:
                raise
            log.warning("Пропущено модуль %s: %s", module_name, e)
    return routes


def build_app() -> Starlette:
    init_db()
    routes = collect_routes()
    routes.append(Mount("/static", app=StaticFiles(directory=str(BASE_DIR / "static")), name="static"))
    routes.append(Mount(MEDIA_URL, app=StaticFiles(directory=str(UPLOAD_DIR)), name="media"))
    middleware = [Middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=60 * 60 * 24 * 30)]
    return Starlette(routes=routes, middleware=middleware)


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
