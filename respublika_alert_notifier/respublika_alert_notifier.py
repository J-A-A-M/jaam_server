import asyncio
import json
import os
import logging

import aiohttp
import redis.asyncio as redis
import sys
from pathlib import Path

try:
    from utils import service_is_fine, set_redis_data, run_with_restart
    from logic import resolve_level
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from utils import service_is_fine, set_redis_data, run_with_restart
    from logic import resolve_level

debug_level = os.environ.get("LOGGING") or "INFO"
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
# Таймаут очікування pub/sub-повідомлення в get_message(). Подія обробляється відразу
# після публікації (не чекає цей інтервал) — таймаут лише задає, як часто ми оновлюємо
# heartbeat і перевіряємо з'єднання, поки тривог немає. Той самий POLL_PERIOD і далі
# читає healthcheck.py для розрахунку MAX_AGE_SECONDS.
poll_period = float(os.environ.get("POLL_PERIOD", 1))
webhook_url = os.environ.get("RESPUBLIKA_ALERTS_WEBHOOK_URL") or ""
test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"

if not webhook_url:
    raise ValueError("RESPUBLIKA_ALERTS_WEBHOOK_URL environment variable is required")
if poll_period < 1:
    raise ValueError("POLL_PERIOD must be >= 1")

# Пауза після невдалого тіка (webhook недоступний, збій Redis тощо), щоб не
# довбити мертвий ендпоінт відразу знову під час тривалого збою.
ERROR_BACKOFF = 10

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

# regionId Києва (regions.json: KIYEW / KYIV_PLCHD-DSTR / KYIV_PLCHD-CITY), як рядок —
# так само зберігається ключ хешу websocket:v1:fusion:alerts:data.
KYIV_REGION_ID = "31"

FUSION_ALERTS_KEY = "websocket:v1:fusion:alerts:data"
# Той самий канал, на який централізовано підписаний redis_fanout у websocket_server —
# публікується при будь-якій зміні fusion-стану алертів (усі регіони, не тільки Київ).
FUSION_ALERTS_UPDATED_CHANNEL = "websocket:v1:fusion:alerts:updated"
LAST_SENT_LEVEL_KEY = "respublika_alert_notifier:last_sent_level"


async def send_webhook(session, level):
    headers = {"Test": "true"} if test_mode else {}
    async with session.get(
        webhook_url, params={"level": level}, headers=headers, timeout=aiohttp.ClientTimeout(total=10)
    ) as response:
        if response.status != 200:
            raise RuntimeError(f"webhook відповів {response.status}: {await response.text()}")


async def check_and_notify(redis_client, session):
    raw = await redis_client.hget(FUSION_ALERTS_KEY, KYIV_REGION_ID)
    flags16 = json.loads(raw) if raw else 0
    level = resolve_level(flags16)

    raw_last_sent = await redis_client.get(LAST_SENT_LEVEL_KEY)
    try:
        last_sent_level = json.loads(raw_last_sent) if raw_last_sent else None
    except json.JSONDecodeError:
        logger.warning(f"⚠️ Пошкоджене значення {LAST_SENT_LEVEL_KEY}={raw_last_sent!r}, скидаю")
        last_sent_level = None

    if level != last_sent_level:
        if last_sent_level is None:
            # Холодний старт (рестарт контейнера, втрата ключа): фіксуємо поточний
            # рівень як базову лінію мовчки. Бот сам дедуплікує за власним
            # персистентним станом, тож реальну зміну ми все одно не пропустимо
            # на наступному тригері — а зайве дублювання на рестарті нам не потрібне.
            await set_redis_data(logger, redis_client, LAST_SENT_LEVEL_KEY, level)
        else:
            logger.info(f"🔔 Рівень тривоги Київ: {last_sent_level} → {level} (flags16={flags16})")
            await send_webhook(session, level)
            await set_redis_data(logger, redis_client, LAST_SENT_LEVEL_KEY, level)
            logger.info(f"✅ Відправлено level={level} на RespublikaChatBot")


async def notify_on_change(redis_client, session):
    # Тригер-driven, консістентно з redis_fanout у websocket_server: підписуємось на
    # канал зміни fusion-алертів замість опитування раз на poll_period. get_message
    # з таймаутом лишається — він не затримує обробку події, а лише задає, як часто
    # оновлюється heartbeat і перевіряється з'єднання, поки тривог немає.
    pubsub = redis_client.pubsub()
    try:
        await pubsub.subscribe(FUSION_ALERTS_UPDATED_CHANNEL)
        logger.info(f"📡 Підписано на {FUSION_ALERTS_UPDATED_CHANNEL}")

        # Перевіряємо поточний стан одразу після підписки, а не лише після першої події —
        # інакше холодний старт чекав би на першу зміну тривоги де завгодно в Україні.
        await check_and_notify(redis_client, session)
        await service_is_fine(logger, redis_client, "respublika_alert_notifier:last_call")

        while True:
            try:
                await pubsub.get_message(ignore_subscribe_messages=True, timeout=poll_period)
                await check_and_notify(redis_client, session)
                await service_is_fine(logger, redis_client, "respublika_alert_notifier:last_call")
            except asyncio.CancelledError:
                raise
            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"⚠️ Redis pub/sub з'єднання втрачено: {e}, перепідключення через {ERROR_BACKOFF}s...")
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
                await asyncio.sleep(ERROR_BACKOFF)
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(FUSION_ALERTS_UPDATED_CHANNEL)
            except Exception as e:
                logger.error(f"❌ Помилка при обробці рівня тривоги Києва: {e}")
                logger.debug("❌ Повний стек помилки:", exc_info=True)
                await asyncio.sleep(ERROR_BACKOFF)
    finally:
        try:
            await pubsub.unsubscribe(FUSION_ALERTS_UPDATED_CHANNEL)
            await pubsub.aclose()
        except Exception:
            pass


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

        async with aiohttp.ClientSession() as session:
            await run_with_restart(
                logger, lambda redis_client: notify_on_change(redis_client, session), redis_client, "notify_on_change"
            )

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
