import asyncio
import os
import logging

import redis.asyncio as redis

debug_level = os.environ.get("LOGGING") or "INFO"
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))

# Канал та повідомлення задаються в конфігу (env), напр. TRIGGER_CHANNEL=releases:production:updated
trigger_channel = os.environ.get("TRIGGER_CHANNEL")
trigger_message = os.environ.get("TRIGGER_MESSAGE", "1")

if not trigger_channel:
    raise ValueError("TRIGGER_CHANNEL environment variable is required")

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)


async def main():
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        decode_responses=True,
        encoding="utf-8",
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )

    try:
        await redis_client.ping()
        logger.info(f"✅ Successfully connected to Redis at {redis_host}:{redis_port}")

        receivers = await redis_client.publish(trigger_channel, trigger_message)
        logger.info(f"📤 Опубліковано '{trigger_message}' в канал '{trigger_channel}' (отримувачів: {receivers})")

    except redis.ConnectionError as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        raise
    finally:
        await redis_client.aclose()
        logger.info("🔌 Redis connection closed")


if __name__ == "__main__":
    asyncio.run(main())
