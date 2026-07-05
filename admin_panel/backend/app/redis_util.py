"""Робота з (можливо кількома) Redis-серверами JAAM.

Логіка дзеркалить maps_online.scan_redis_clients та utils.get_redis_data_by_pattern,
але повертає повні значення клієнтів (не лише connect_time), бо адмінці потрібні всі поля.
"""

import json
import logging

import redis.asyncio as redis

from .config import parse_redis_hosts, redis_name

logger = logging.getLogger("admin_panel.redis")

CLIENTS_PATTERN = "websocket:clients:*"


class RedisServer:
    def __init__(self, name: str, client: redis.Redis):
        self.name = name
        self.client = client


def build_servers() -> list[RedisServer]:
    servers: list[RedisServer] = []
    for idx, cfg in enumerate(parse_redis_hosts()):
        client = redis.Redis(
            host=cfg.get("host", "redis"),
            port=int(cfg.get("port", 6379)),
            db=int(cfg.get("db", 0)),
            password=cfg.get("password", "redis"),
            decode_responses=True,
            encoding="utf-8",
            socket_connect_timeout=5,
            socket_keepalive=True,
            health_check_interval=30,
        )
        servers.append(RedisServer(redis_name(cfg, idx), client))
        logger.info(
            "Redis-сервер налаштовано: %s (%s:%s)",
            redis_name(cfg, idx),
            cfg.get("host"),
            cfg.get("port"),
        )
    return servers


async def _read_value(client: redis.Redis, key: str) -> dict | None:
    """Читає значення клієнта незалежно від типу (JSON-string або hash)."""
    key_type = await client.type(key)
    if key_type == "string":
        raw = await client.get(key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    if key_type == "hash":
        raw = await client.hgetall(key)
        out = {}
        for k, v in raw.items():
            try:
                out[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                out[k] = v
        return out
    return None


_KEY_PREFIX = "websocket:clients:"


def _ip_from_key(key: str) -> str | None:
    """Витягує IP з ключа 'websocket:clients:{ip}:{client_id}'.
    Використовує rsplit щоб не ламати IPv6-адреси."""
    rest = key[len(_KEY_PREFIX) :]
    parts = rest.rsplit(":", 1)
    return parts[0] if len(parts) == 2 else None


async def scan_clients(client: redis.Redis) -> list[dict]:
    """Повертає список значень усіх websocket:clients:* на одному Redis."""
    result: list[dict] = []
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match=CLIENTS_PATTERN, count=100)
        for key in keys:
            try:
                value = await _read_value(client, key)
                if value:
                    value["ip"] = _ip_from_key(key)
                    result.append(value)
            except Exception as exc:  # noqa: BLE001
                logger.error("Помилка читання ключа %s: %s", key, exc)
        if cursor == 0:
            break
    return result


async def count_clients(client: redis.Redis) -> int:
    """Кількість онлайн-клієнтів (дзеркалить websocket_server.count_clients_in_redis)."""
    total = 0
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor, match=CLIENTS_PATTERN, count=1000)
        total += len(keys)
        if cursor == 0:
            break
    return total
