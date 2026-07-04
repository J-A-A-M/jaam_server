"""Конфігурація адмін-панелі з env (сумісна з патерном інших сервісів JAAM)."""

import json
import logging
import os

logger = logging.getLogger("admin_panel.config")


def _env(key: str, default: str | None = None) -> str | None:
    value = os.environ.get(key)
    return value if value not in (None, "") else default


# --- Загальне ---
LOG_LEVEL = _env("LOGGING", "INFO")
PORT = int(_env("PORT", "8099"))

# --- База даних ---
# Приклад: postgresql+asyncpg://jaam:jaam@postgres:5432/jaam_admin
DATABASE_URL = _env(
    "DATABASE_URL",
    "postgresql+asyncpg://jaam:jaam@postgres:5432/jaam_admin",
)

# --- Авторизація ---
JWT_SECRET = _env("JWT_SECRET", "change-me-in-production")
JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = int(_env("JWT_TTL_SECONDS", str(7 * 24 * 3600)))
COOKIE_NAME = "jaam_admin_token"
COOKIE_SECURE = _env("COOKIE_SECURE", "false").lower() == "true"

# Сідовий адміністратор (створюється при старті, якщо користувачів немає)
ADMIN_USER = _env("ADMIN_USER", "admin")
ADMIN_PASSWORD = _env("ADMIN_PASSWORD", "jaam_rocks")

# --- Collector ---
COLLECT_INTERVAL = int(_env("COLLECT_INTERVAL", "20"))  # секунд між сканами
# Пристрій вважається офлайн, якщо його не бачили довше за цей поріг (> Redis TTL 120с)
OFFLINE_AFTER_SECONDS = int(_env("OFFLINE_AFTER_SECONDS", "150"))

# Часовий пояс, у якому websocket_server пише connect_time (без TZ-суфікса)
SERVER_TZ = _env("SERVER_TZ", "Europe/Kyiv")


# --- Redis (можливо декілька серверів) ---
# REDIS_HOSTS: JSON-масив [{"host","port","password","db","name"}, ...]
# або одиночні REDIS_HOST/REDIS_PORT/REDIS_PASSWORD/REDIS_DB
_redis_hosts_raw = _env("REDIS_HOSTS")
_redis_host = _env("REDIS_HOST", "redis")
_redis_port = int(_env("REDIS_PORT", "6379"))
_redis_password = _env("REDIS_PASSWORD", "redis")
_redis_db = int(_env("REDIS_DB", "0"))


def parse_redis_hosts() -> list[dict]:
    """Повертає список конфігів Redis. Перевикористовує підхід maps_online.parse_redis_hosts."""
    if _redis_hosts_raw:
        try:
            hosts = json.loads(_redis_hosts_raw)
            if isinstance(hosts, list) and hosts:
                return hosts
        except json.JSONDecodeError:
            logger.error("REDIS_HOSTS не є валідним JSON, використовую одиночний REDIS_HOST")
    return [
        {
            "host": _redis_host,
            "port": _redis_port,
            "password": _redis_password,
            "db": _redis_db,
            "name": _redis_host,
        }
    ]


def redis_name(cfg: dict, idx: int) -> str:
    return cfg.get("name") or cfg.get("host") or f"server-{idx + 1}"
