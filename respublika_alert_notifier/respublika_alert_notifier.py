import asyncio
import json
import os
import logging

import aiohttp
import redis.asyncio as redis
import sys
from pathlib import Path

try:
    from utils import service_is_fine, run_with_restart
    from logic import resolve_level
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from utils import service_is_fine, run_with_restart
    from respublika_alert_notifier.logic import resolve_level

debug_level = os.environ.get("LOGGING") or "INFO"
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
poll_period = float(os.environ.get("POLL_PERIOD", 1))
webhook_url = os.environ.get("RESPUBLIKA_ALERTS_WEBHOOK_URL") or ""
test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"

if not webhook_url:
    raise ValueError("RESPUBLIKA_ALERTS_WEBHOOK_URL environment variable is required")

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

# regionId Києва (regions.json: KIYEW / KYIV_PLCHD-DSTR / KYIV_PLCHD-CITY), як рядок —
# так само зберігається ключ хешу websocket:v1:fusion:alerts:data.
KYIV_REGION_ID = "31"

FUSION_ALERTS_KEY = "websocket:v1:fusion:alerts:data"
LAST_SENT_LEVEL_KEY = "respublika_alert_notifier:last_sent_level"


async def send_webhook(session, level):
    headers = {"Test": "true"} if test_mode else {}
    async with session.get(
        webhook_url, params={"level": level}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"webhook відповів {response.status}: {await response.text()}")


async def notify_on_change(redis_client):
    while True:
        try:
            raw = await redis_client.hget(FUSION_ALERTS_KEY, KYIV_REGION_ID)
            flags16 = json.loads(raw) if raw else 0
            level = resolve_level(flags16)

            raw_last_sent = await redis_client.get(LAST_SENT_LEVEL_KEY)
            last_sent_level = json.loads(raw_last_sent) if raw_last_sent else None

            if level != last_sent_level:
                if last_sent_level is None and level == "green":
                    # Холодний старт без активної тривоги: фіксуємо базову лінію мовчки,
                    # щоб рестарт контейнера не слав зайве "відбій" в чат.
                    await redis_client.set(LAST_SENT_LEVEL_KEY, json.dumps(level))
                else:
                    logger.info(f"🔔 Рівень тривоги Київ: {last_sent_level} → {level} (flags16={flags16})")
                    async with aiohttp.ClientSession() as session:
                        await send_webhook(session, level)
                    await redis_client.set(LAST_SENT_LEVEL_KEY, json.dumps(level))
                    logger.info(f"✅ Відправлено level={level} на {webhook_url}")

            await service_is_fine(logger, redis_client, "respublika_alert_notifier:last_call")
            await asyncio.sleep(poll_period)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"❌ Помилка при обробці рівня тривоги Києва: {e}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)
            await asyncio.sleep(poll_period)


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
        if test_mode:
            logger.warning("🧪 TEST_MODE увімкнено: усі вебхуки йдуть з заголовком Test: true")

        await run_with_restart(logger, notify_on_change, redis_client, "notify_on_change")

    except redis.ConnectionError as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")
        raise
    except asyncio.exceptions.CancelledError:
        logger.info("⏹️  App stopped by user")
    finally:
        await redis_client.aclose()
        logger.info("🔌 Redis connection closed")


if __name__ == "__main__":
    asyncio.run(main())
