"""Робота з (можливо кількома) Redis-серверами JAAM.

Логіка дзеркалить maps_online.scan_redis_clients та utils.get_redis_data_by_pattern,
але повертає повні значення клієнтів (не лише connect_time), бо адмінці потрібні всі поля.
"""

import asyncio
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


def build_server_from_config(cfg) -> RedisServer:
    """Будує RedisServer з ORM-об'єкта RedisServerConfig (duck typing, без циклічного імпорту)."""
    client = redis.Redis(
        host=cfg.host,
        port=cfg.port,
        db=cfg.db,
        password=cfg.password or None,
        decode_responses=True,
        encoding="utf-8",
        socket_connect_timeout=5,
        socket_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )
    logger.info("Redis-сервер: %s (%s:%s)", cfg.name, cfg.host, cfg.port)
    return RedisServer(cfg.name, client)


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


DEVICE_AUTH_REVOKED_CHANNEL = "device:auth:revoked"


async def mirror_device_auth(servers: list[RedisServer], chip_id: str, secret_version: int, whitelisted: bool) -> None:
    """Дзеркалить {version, whitelisted} для chip_id у device_auth:<CHIP_ID> на всі сервери.

    Postgres (jaam_maps) — одна спільна база без поділу на середовища, тому пишемо
    на ВСІ enabled сервери без винятків (не "prod чи dev" рішення, а консистентне
    дзеркалювання єдиного джерела правди в кожен кеш, який його читає: websocket_server
    та update_server). Жодного секретного матеріалу тут немає — лише версія й прапорець,
    сам секрет — похідний (device_auth.derive_device_secret) і ніде не зберігається.

    Whitelist перевіряється websocket_server лише один раз, у process_request() перед WS
    upgrade - без явного kick-сигналу вже підключений пристрій лишався б живим аж до
    власного наступного реконекту. Публікуємо chip_id у DEVICE_AUTH_REVOKED_CHANNEL (лише
    коли знімаємо whitelisted, не при видачі/поновленні) - websocket_server.alerts_data_touch
    звіряє його зі своїм з'єднанням і форсує close(), якщо збігається.
    """
    key = f"device_auth:{chip_id.upper()}"
    mapping = {
        "version": str(secret_version),
        "whitelisted": "1" if whitelisted else "0",
    }

    async def _mirror_one(server: RedisServer) -> None:
        try:
            await server.client.hset(key, mapping=mapping)
            if not whitelisted:
                await server.client.publish(DEVICE_AUTH_REVOKED_CHANNEL, chip_id.upper())
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не вдалося дзеркалити device_auth для %s на %s: %s",
                chip_id,
                server.name,
                exc,
            )

    # Незалежні Redis-сервери/хости - пишемо конкурентно, а не по черзі (N x RTT).
    await asyncio.gather(*(_mirror_one(server) for server in servers))


async def mirror_claim_code(servers: list[RedisServer], chip_id: str, code_hash: str, ttl_s: int) -> None:
    """Пише одноразовий квиток активації device_claim:<CHIP_ID> ({code_hash, attempts=0}, TTL)
    на всі сервери - update_server's /touch/claim звіряє код пристрою з ним і сам похідний
    секрет (не тут) віддає за matching-ом. TTL - єдине джерело "минув термін дії", Postgres
    нічого про сам код не зберігає (лише secret_version, який уже мирориться mirror_device_auth
    окремим викликом до цього)."""
    key = f"device_claim:{chip_id.upper()}"

    async def _mirror_one(server: RedisServer) -> None:
        try:
            async with server.client.pipeline(transaction=False) as pipe:
                pipe.hset(key, mapping={"code_hash": code_hash, "attempts": "0"})
                pipe.expire(key, ttl_s)
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не вдалося дзеркалити claim-код для %s на %s: %s",
                chip_id,
                server.name,
                exc,
            )

    await asyncio.gather(*(_mirror_one(server) for server in servers))


async def delete_claim_code(servers: list[RedisServer], chip_id: str) -> None:
    """Видаляє device_claim:<CHIP_ID> на всіх серверах. Викликається при знятті whitelisted -
    інакше вже видний, ще не активований claim-код лишався б робочим і після ревокації
    (claim_touch_secret сам собою цього не знає, доки не звернеться до device_auth)."""
    key = f"device_claim:{chip_id.upper()}"

    async def _delete_one(server: RedisServer) -> None:
        try:
            await server.client.delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Не вдалося видалити claim-код для %s на %s: %s",
                chip_id,
                server.name,
                exc,
            )

    await asyncio.gather(*(_delete_one(server) for server in servers))
