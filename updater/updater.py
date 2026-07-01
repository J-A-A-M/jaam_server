import json
import os
import asyncio
import logging
import datetime

import redis.asyncio as redis
import sys
from pathlib import Path

try:
    from utils import (
        get_redis_data,
        set_redis_data,
        run_with_restart,
        get_file_names,
        release_filter,
        beta_filter,
        Debouncer,
        Throttler,
        TYPE_ALERTS_BATCH,
        TYPE_NOTIFICATIONS_BATCH,
    )
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    from utils import (
        get_redis_data,
        set_redis_data,
        run_with_restart,
        get_file_names,
        release_filter,
        beta_filter,
        Debouncer,
        Throttler,
        TYPE_ALERTS_BATCH,
        TYPE_NOTIFICATIONS_BATCH,
    )

# Модулі обробки даних. Flat-імпорт (docker: `python updater.py`) з fallback
# на пакетний (`updater.updater`, як у тестах).
try:
    from pubsub_loop import run_pubsub_loop
    from files import sync_local_files
    from processing import (
        common,
        alerts,
        etryvoga,
        weather,
        energy,
        radiation,
        releases,
        notifications,
        corrections,
    )
except ImportError:
    from updater.pubsub_loop import run_pubsub_loop
    from updater.files import sync_local_files
    from updater.processing import (
        common,
        alerts,
        etryvoga,
        weather,
        energy,
        radiation,
        releases,
        notifications,
        corrections,
    )

# Імпорт regions.json - спочатку з поточної папки, потім з батьківської
regions = {}
try:
    # Спочатку пробуємо завантажити з поточної папки (updater/regions.json)
    regions_path = Path(__file__).resolve().parent / "regions.json"
    with open(regions_path, "r", encoding="utf-8") as f:
        regions = json.load(f)
except FileNotFoundError:
    # Якщо не знайдено, пробуємо завантажити з батьківської папки (../regions.json)
    try:
        regions_path = Path(__file__).resolve().parent.parent / "regions.json"
        with open(regions_path, "r", encoding="utf-8") as f:
            regions = json.load(f)
    except FileNotFoundError:
        # Якщо regions.json не знайдено взагалі, залишаємо порожній словник
        logging.warning("regions.json not found, using empty regions dict")

version = 4

debug_level = os.environ.get("LOGGING") or "INFO"
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
shared_path = os.environ.get("SHARED_PATH") or "/shared_data/releases"
shared_path_beta = os.environ.get("SHARED_PATH_BETA") or "/shared_data/beta"
sink_local_files = os.environ.get("SINK_LOCAL_FILES", "True").lower() == "true"
fusion_alerts_debounce = float(os.environ.get("FUSION_ALERTS_DEBOUNCE", 1))
fusion_alerts_throttle = float(os.environ.get("FUSION_ALERTS_THROTTLE", 0))
fusion_etryvoga_throttle = float(os.environ.get("FUSION_ETRYVOGA_THROTTLE", 0))

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

LEGACY_LED_COUNT = 28


async def get_cache_data(mc, key_b, default_response=None):
    if default_response is None:
        default_response = {}

    cache = await mc.get(key_b)

    if cache:
        cache = json.loads(cache.decode("utf-8"))
    else:
        cache = default_response

    return cache


async def get_byte_data(mc, key_b, default_response=None):
    if default_response is None:
        default_response = b""

    cache = await mc.get(key_b)

    if not cache:
        cache = default_response

    return cache


def get_current_datetime():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_current_timestamp():
    return int(datetime.datetime.now(datetime.UTC).timestamp())


async def update_websocket_v1_alerts(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            alerts_cache = await get_redis_data(logger, redis_client, "alerts:api:data", default_response=[])

            data = alerts.build_v1_alerts(alerts_cache, regions, LEGACY_LED_COUNT)

            logger.debug("💾 Зберігаємо websocket:v1:legacy:alerts")
            await set_redis_data(logger, redis_client, "websocket:v1:legacy:alerts", data)
            await redis_client.publish("websocket:v1:legacy:alerts:updated", "1")
            logger.info("✅ websocket:v1:legacy:alerts збережено")
        except Exception as e:
            logger.error(f"❌ update_websocket_v1_alerts (process_alerts) error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["alerts:api:updated"],
        process,
        "update_websocket_v1_alerts",
        logger,
        run_once=run_once,
    )


async def update_websocket_v2_alerts(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            alerts_cache, websocket = await asyncio.gather(
                get_redis_data(logger, redis_client, "alerts:api:data", default_response=[]),
                get_redis_data(
                    logger,
                    redis_client,
                    "websocket:v2:legacy:alerts",
                    default_response=[[0, 1645674000]] * LEGACY_LED_COUNT,
                ),
            )

            data = alerts.build_v2_alerts(alerts_cache, websocket, regions, LEGACY_LED_COUNT)

            common.check_states(data, websocket, get_current_timestamp())
            logger.debug("💾 Зберігаємо websocket:v2:legacy:alerts")
            await set_redis_data(logger, redis_client, "websocket:v2:legacy:alerts", data)
            await redis_client.publish("websocket:v2:legacy:alerts:updated", "1")
            logger.info("✅ websocket:v2:legacy:alerts збережено")
        except Exception as e:
            logger.error(f"❌ update_websocket_v2_alerts (process_alerts) error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["alerts:api:updated"],
        process,
        "update_websocket_v2_alerts",
        logger,
        run_once=run_once,
    )


async def ertyvoga_v1(redis_client, cache_key, data_key, alert_key=None):
    # Отримуємо значення паралельно (одночасно, але з правильною обробкою типів)
    cache, websocket = await asyncio.gather(
        get_redis_data(logger, redis_client, cache_key, default_response={}),
        get_redis_data(logger, redis_client, data_key, default_response=[1645674000] * LEGACY_LED_COUNT),
    )
    alerts_websocket = None
    if alert_key:
        alerts_websocket = await get_redis_data(
            logger, redis_client, alert_key, default_response=[[0, 1645674000]] * LEGACY_LED_COUNT
        )

    data = etryvoga.build_etryvoga_v1_data(cache, alerts_websocket, regions, LEGACY_LED_COUNT)

    logger.debug(f"⚠️ {data_key} DATA NEW: {data}")
    logger.debug(f"⚠️ {data_key} DATA OLD: {websocket}")
    if websocket != data:
        common.check_notifications(data, websocket)
        logger.debug(f"💾 Зберігаємо {data_key}")
        await set_redis_data(logger, redis_client, data_key, data)
        await redis_client.publish(f"{data_key}:updated", "1")
        logger.info(f"✅ {data_key} збережено")
    else:
        logger.info(f"ℹ️  {data_key} не змінився")


async def update_websocket_v1_etryvoga(redis_client, run_once=False):
    channel_config = {
        "alerts:etryvoga:drones:updated": (
            "alerts:etryvoga:drones:data",
            "websocket:v1:legacy:drones",
            "websocket:v2:legacy:drones",
        ),
        "alerts:etryvoga:missiles:updated": (
            "alerts:etryvoga:missiles:data",
            "websocket:v1:legacy:missiles",
            "websocket:v2:legacy:missiles",
        ),
        "alerts:etryvoga:kabs:updated": (
            "alerts:etryvoga:kabs:data",
            "websocket:v1:legacy:kabs",
            None,
        ),
        "alerts:etryvoga:explosions:updated": (
            "alerts:etryvoga:explosions:data",
            "websocket:v1:legacy:explosions",
            None,
        ),
    }

    async def process(channel):
        if channel in channel_config:
            cache_key, data_key, alert_key = channel_config[channel]
            await ertyvoga_v1(redis_client, cache_key, data_key, alert_key)

    await run_pubsub_loop(
        redis_client,
        list(channel_config.keys()),
        process,
        "update_websocket_v1_etryvoga",
        logger,
        run_once=run_once,
    )


async def update_websocket_v1_weather(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            cache = await get_redis_data(logger, redis_client, "weather:openweathermap:data", default_response=[])

            data = weather.build_v1_weather(cache, regions, LEGACY_LED_COUNT)

            logger.debug("💾 Зберігаємо websocket:v1:legacy:weather")
            await set_redis_data(logger, redis_client, "websocket:v1:legacy:weather", data)
            await redis_client.publish("websocket:v1:legacy:weather:updated", "1")
            logger.info("✅ websocket:v1:legacy:weather збережено")
        except Exception as e:
            logger.error(f"❌ update_weather_openweathermap_v1 (process): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["weather:openweathermap:updated"],
        process,
        "update_websocket_v1_weather",
        logger,
        run_once=run_once,
    )


async def alert_reasons_v1(redis_client, alert_type, cache_key, default_value):
    # Отримуємо значення паралельно (одночасно, але з правильною обробкою типів)
    reasons_cache, websocket_data, alerts_cache = await asyncio.gather(
        get_redis_data(logger, redis_client, "alerts:http:reasons:data", default_response={}),
        get_redis_data(logger, redis_client, cache_key, default_response=default_value),
        get_redis_data(logger, redis_client, "alerts:api:data", default_response=[]),
    )
    reasons = reasons_cache.get("reasons", [])
    now = get_current_timestamp()

    data = alerts.build_alert_reasons(reasons, alerts_cache, websocket_data, default_value, alert_type, regions, now)

    logger.debug(f"⚠️ {cache_key} DATA NEW: {data}")
    logger.debug(f"⚠️ {cache_key} DATA OLD: {websocket_data}")

    if websocket_data != data:
        common.check_states(data, websocket_data, now)
        logger.debug(f"💾 Зберігаємо {cache_key}")
        await set_redis_data(logger, redis_client, cache_key, data)
        await redis_client.publish(f"{cache_key}:updated", "1")
        logger.info(f"✅ {cache_key} збережено")
    else:
        logger.info(f"ℹ️  {cache_key} не змінився")


async def update_websocket_v2_etryvoga(redis_client, run_once=False):
    reason_targets = [
        ("Drones", "websocket:v2:legacy:drones"),
        ("Missile", "websocket:v2:legacy:missiles"),
    ]

    async def process(_channel=None):
        for alert_type, cache_key in reason_targets:
            await alert_reasons_v1(
                redis_client,
                alert_type,
                cache_key,
                [[0, 1645674000]] * LEGACY_LED_COUNT,
            )

    await run_pubsub_loop(
        redis_client,
        ["alerts:http:reasons:updated", "alerts:api:updated"],
        process,
        "update_websocket_v2_etryvoga",
        logger,
        run_once=run_once,
    )


async def update_websocket_v1_energy(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            cache, websocket = await asyncio.gather(
                get_redis_data(logger, redis_client, "energy:ukrenergo:data", default_response=[]),
                get_redis_data(
                    logger,
                    redis_client,
                    "websocket:v1:legacy:energy",
                    default_response=[[0, 1645674000]] * LEGACY_LED_COUNT,
                ),
            )

            data = energy.build_v1_energy(cache, websocket, regions, get_current_timestamp(), LEGACY_LED_COUNT)

            logger.debug("💾 Зберігаємо websocket:v1:legacy:energy")
            await set_redis_data(logger, redis_client, "websocket:v1:legacy:energy", data)
            await redis_client.publish("websocket:v1:legacy:energy:updated", "1")
            logger.info("✅ websocket:v1:legacy:energy збережено")
        except Exception as e:
            logger.error(f"update_websocket_v1_energy(process): {str(e)}")
            logger.debug("Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["energy:ukrenergo:updated"],
        process,
        "update_websocket_v1_energy",
        logger,
        run_once=run_once,
    )


async def update_websocket_v1_radiation(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            data_cache, sensors_cache = await asyncio.gather(
                get_redis_data(logger, redis_client, "radiation:saveecobot:data:data", default_response=[]),
                get_redis_data(
                    logger,
                    redis_client,
                    "radiation:saveecobot:sensors:data",
                    default_response={"states": {}, "info": {"last_update": None}},
                ),
            )

            data = radiation.build_v1_radiation(data_cache, sensors_cache, regions, LEGACY_LED_COUNT)

            logger.debug("💾 Зберігаємо websocket:v1:legacy:radiation")
            await set_redis_data(logger, redis_client, "websocket:v1:legacy:radiation", data)
            await redis_client.publish("websocket:v1:legacy:radiation:updated", "1")
            logger.info("✅ websocket:v1:legacy:radiation збережено")
        except Exception as e:
            logger.error(f"❌ update_websocket_v1_radiation(process): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["radiation:saveecobot:updated"],
        process,
        "update_websocket_v1_radiation",
        logger,
        run_once=run_once,
    )


async def update_websocket_v1_global_notifications(redis_client, run_once=False):
    async def process(_channel=None):
        try:
            cache, websocket = await asyncio.gather(
                get_redis_data(logger, redis_client, "alerts:ws:alerts:data", default_response=[]),
                get_redis_data(logger, redis_client, "websocket:v1:legacy:global_notifications", default_response={}),
            )

            data = notifications.build_global_notifications(cache)
            if data != websocket:
                logger.debug("💾 Зберігаємо websocket:v1:legacy:global_notifications")
                await set_redis_data(logger, redis_client, "websocket:v1:legacy:global_notifications", data)
                await redis_client.publish("websocket:v1:legacy:global_notifications:updated", "1")
                logger.info("✅ websocket:v1:legacy:global_notifications збережено")
            else:
                logger.info("ℹ️  websocket:v1:legacy:global_notifications не змінився")
        except Exception as e:
            logger.error(f"❌ update_global_notifications_v1(process): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["alerts:ws:alerts:updated"],
        process,
        "update_websocket_v1_global_notifications",
        logger,
        run_once=run_once,
    )


async def update_releases_v1(redis_client, run_once=False):
    async def process_releases():
        try:
            releases_cache, stored_data = await asyncio.gather(
                get_redis_data(logger, redis_client, "releases:data", default_response=[]),
                get_redis_data(logger, redis_client, "releases:production", default_response={}),
            )

            data = releases.select_release_files(
                releases_cache,
                lambda r: not r["prerelease"] and release_filter(r["name"]),
                get_file_names,
                logger,
                strip_pattern="JAAM_",
                limit=5,
            )
            if data != stored_data:
                # Синхронізуємо локальні файли з GitHub
                if sink_local_files:
                    await sync_local_files(data, shared_path)

                logger.debug("💾 Зберігаємо releases:production")
                await set_redis_data(logger, redis_client, "releases:production", data)
                await redis_client.publish("releases:production:updated", "1")
                logger.info("✅ releases:production збережено")
            else:
                logger.info("ℹ️  releases:production не змінився")
        except Exception as e:
            logger.error(f"❌ update_releases_v1(process_releases): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    async def process_beta():
        try:
            releases_cache, stored_data = await asyncio.gather(
                get_redis_data(logger, redis_client, "releases:data", default_response=[]),
                get_redis_data(logger, redis_client, "releases:beta", default_response={}),
            )

            data = releases.select_release_files(
                releases_cache,
                lambda r: beta_filter(r["name"]),
                get_file_names,
                logger,
                strip_pattern="JAAM_",
                limit=10,
            )
            if data != stored_data:
                # Синхронізуємо локальні файли з GitHub
                if sink_local_files:
                    await sync_local_files(data, shared_path_beta)

                logger.debug("💾 Зберігаємо releases:beta")
                await set_redis_data(logger, redis_client, "releases:beta", data)
                await redis_client.publish("releases:beta:updated", "1")
                logger.info("✅ releases:beta збережено")
            else:
                logger.info("ℹ️  releases:beta не змінився")
        except Exception as e:
            logger.error(f"❌ update_releases_v1(process_beta): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    async def process(_channel=None):
        await asyncio.gather(process_releases(), process_beta())

    await run_pubsub_loop(
        redis_client,
        ["releases:data:updated"],
        process,
        "update_releases_v1",
        logger,
        run_once=run_once,
    )


async def update_websocket_fusion_v1_alerts(redis_client, run_once=False):
    async def process_alerts(_channel=None):
        try:
            # Отримуємо всі значення паралельно (одночасно, але з правильною обробкою типів)
            (
                alerts_cache,
                reasons_http_cache,
                old_state,
                alerts_hash_actual,
            ) = await asyncio.gather(
                get_redis_data(logger, redis_client, "alerts:api:data", default_response=[]),
                get_redis_data(logger, redis_client, "alerts:http:reasons:data", default_response={}),
                get_redis_data(logger, redis_client, "websocket:v1:fusion:alerts:data", default_response={}),
                get_redis_data(logger, redis_client, "websocket:v1:fusion:alerts:hash_actual", default_response=0),
            )
            logger.info(f"🔍 process_alerts: hash_actual_read={alerts_hash_actual}, old_state={old_state}")

            reasons = reasons_http_cache.get("reasons", [])

            new_state = alerts.build_fusion_alerts_state(alerts_cache, reasons)
            logger.debug(f"⚠️ ALERTS FUSION DATA: {new_state}")
            if new_state != old_state:
                changed_region_ids = alerts.find_changed_regions(old_state, new_state)
                empty_region_ids = alerts.find_empty_regions(old_state, new_state)

                alerts_payload, alerts_hash_current = alerts.build_alerts_payload(
                    new_state, changed_region_ids, empty_region_ids, alerts_hash_actual, TYPE_ALERTS_BATCH
                )

                logger.debug("💾 Зберігаємо websocket:v1:fusion:alerts:data")
                async with redis_client.pipeline(transaction=True) as pipe:
                    pipe.set("websocket:v1:fusion:payload:alerts", json.dumps(alerts_payload.hex()))
                    pipe.delete("websocket:v1:fusion:alerts:data")
                    for k, v in new_state.items():
                        pipe.hset("websocket:v1:fusion:alerts:data", k, json.dumps(v))
                    pipe.set("websocket:v1:fusion:alerts:hash_actual", json.dumps(alerts_hash_current))
                    pipe.set("websocket:v1:fusion:alerts:hash_previous", json.dumps(alerts_hash_actual))
                    await pipe.execute()
                await redis_client.publish("websocket:v1:fusion:alerts:updated", str(alerts_hash_current))
                logger.info(
                    f"✅ websocket:v1:fusion:alerts:data збережено (hash_prev={alerts_hash_actual} → hash_curr={alerts_hash_current})"
                )
            else:
                logger.info("ℹ️  websocket:v1:fusion:alerts:data не змінився")

        except Exception as e:
            logger.error(f"❌ process_alerts error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    throttler = Throttler(fusion_alerts_throttle)

    async def on_message(_channel):
        await throttler.call(process_alerts)

    # initial=process_alerts: початковий запуск після підписки (на випадок пропущених подій при рестарті)
    await run_pubsub_loop(
        redis_client,
        ["alerts:api:updated", "alerts:http:reasons:updated"],
        on_message,
        "update_websocket_fusion_v1_alerts",
        logger,
        run_once=run_once,
        initial=process_alerts,
        throttler=throttler,
        sleep=None,
    )


async def update_websocket_fusion_v1_etryvoga(redis_client, run_once=False):
    async def process_etryvoga(_channel=None):
        try:
            alerts_cache, last_processed_id = await asyncio.gather(
                get_redis_data(logger, redis_client, "alerts:etryvoga:full:data", default_response=[]),
                get_redis_data(logger, redis_client, "websocket:v1:fusion:etryvoga:last_processed_id", 0),
            )

            data, first_processed_id = etryvoga.build_fusion_v1_etryvoga(alerts_cache, last_processed_id)
            logger.debug(f"⚠️ ETRYVOGA FUSION DATA: {data}")
            if data:
                payload_hex = etryvoga.build_notifications_payload(
                    list(data.keys()), TYPE_NOTIFICATIONS_BATCH, lambda rid: data.get(rid, 0)
                )
                logger.debug("💾 Зберігаємо websocket:v1:fusion:etryvoga:data")
                await asyncio.gather(
                    set_redis_data(logger, redis_client, "websocket:v1:fusion:payload:notifications", payload_hex),
                    set_redis_data(logger, redis_client, "websocket:v1:fusion:etryvoga:data", data),
                    set_redis_data(
                        logger, redis_client, "websocket:v1:fusion:etryvoga:last_processed_id", first_processed_id
                    ),
                )
                await redis_client.publish("websocket:v1:fusion:etryvoga:updated", "1")
                logger.info("✅ websocket_fusion_v1_etryvoga збережено")
            else:
                logger.info("ℹ️  websocket_fusion_v1_etryvoga не змінився")

        except Exception as e:
            logger.error(f"❌ process_etryvoga: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    throttler = Throttler(fusion_etryvoga_throttle)

    async def on_message(_channel):
        await throttler.call(process_etryvoga)

    await run_pubsub_loop(
        redis_client,
        ["alerts:etryvoga:updated"],
        on_message,
        "update_websocket_fusion_v1_etryvoga",
        logger,
        run_once=run_once,
        throttler=throttler,
    )


async def update_websocket_fusion_v2_etryvoga(redis_client, run_once=False):
    channel_config = {
        "alerts:etryvoga_ws:drones:updated": ("alerts:etryvoga_ws:drones:data", 1 << 5),
        "alerts:etryvoga_ws:missiles:updated": ("alerts:etryvoga_ws:missiles:data", 1 << 6),
        "alerts:etryvoga_ws:kabs:updated": ("alerts:etryvoga_ws:kabs:data", 1 << 7),
        "alerts:etryvoga_ws:explosions:updated": ("alerts:etryvoga_ws:explosions:data", 1 << 9),
        "alerts:etryvoga_ws:recons:updated": ("alerts:etryvoga_ws:recons:data", 1 << 10),
    }

    throttler = Throttler(fusion_etryvoga_throttle)
    pending_channels: set[str] = set()

    async def process_channel(data_key: str, bit: int):
        try:
            type_data = await get_redis_data(logger, redis_client, data_key, default_response={})

            logger.debug(f"⚠️ ETRYVOGA FUSION V2 DATA (bit={bit:#x}): {type_data}")

            if type_data:
                region_names = []
                for rid_str in type_data:
                    name, _ = common.convert_region_ids(regions, int(rid_str), "regionId", "legacyId")
                    region_names.append(name or rid_str)
                payload_hex = etryvoga.build_notifications_payload(
                    list(type_data), TYPE_NOTIFICATIONS_BATCH, lambda rid: bit
                )
                logger.debug("💾 Зберігаємо websocket:v1:fusion:payload:notifications")
                await set_redis_data(
                    logger,
                    redis_client,
                    "websocket:v1:fusion:payload:notifications",
                    payload_hex,
                )
                await redis_client.publish("websocket:v1:fusion:etryvoga:updated", "1")
                logger.info(f"✅ websocket_fusion_v2_etryvoga збережено (bit={bit:#x}): {', '.join(region_names)}")
            else:
                logger.info(f"ℹ️  websocket_fusion_v2_etryvoga немає даних (bit={bit:#x})")

        except Exception as e:
            logger.error(f"❌ process_channel v2 ({data_key}): {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    async def drain():
        channels_to_process = list(pending_channels)
        pending_channels.clear()
        for ch in channels_to_process:
            data_key, bit = channel_config[ch]
            await process_channel(data_key, bit)

    async def on_message(channel):
        pending_channels.add(channel)
        await throttler.call(drain)

    await run_pubsub_loop(
        redis_client,
        list(channel_config.keys()),
        on_message,
        "update_websocket_fusion_v2_etryvoga",
        logger,
        run_once=run_once,
        throttler=throttler,
        accepted_channels=set(channel_config.keys()),
    )


async def update_websocket_fusion_v1_openweathermap(redis_client, run_once=False):
    async def process_weather(_channel=None):
        try:
            weather_cache = await get_redis_data(
                logger, redis_client, "weather:openweathermap:data", default_response={}
            )

            data = weather.build_fusion_weather(
                weather_cache, lambda region: region["region"]["regionId"], lambda region: region.get("temp")
            )

            logger.debug(f"⚠️ WEATHER FUSION DATA: {data}")
            logger.debug("💾 Зберігаємо websocket:v1:fusion:openweathermap:data")
            await set_redis_data(logger, redis_client, "websocket:v1:fusion:openweathermap:data", data)
            await redis_client.publish("websocket:v1:fusion:openweathermap:updated", "1")
            logger.info("✅ websocket:v1:fusion:openweathermap:data збережено")
        except Exception as e:
            logger.error(f"❌ process_weather error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["weather:openweathermap:updated"],
        process_weather,
        "update_websocket_fusion_v1_openweathermap",
        logger,
        run_once=run_once,
    )


async def update_websocket_fusion_v1_energy(redis_client, run_once=False):
    async def process_energy(_channel=None):
        try:
            energy_cache = await get_redis_data(logger, redis_client, "energy:ukrenergo:data", default_response=[])

            data = energy.build_fusion_energy(energy_cache)
            corrections.apply_region_corrections(data, corrections.ENERGY_CORRECTIONS)

            logger.debug(f"⚠️ ENERGY FUSION DATA: {data}")
            logger.debug("💾 Зберігаємо websocket:v1:fusion:energy:data")
            await set_redis_data(logger, redis_client, "websocket:v1:fusion:energy:data", data)
            await redis_client.publish("websocket:v1:fusion:energy:updated", "1")
            logger.info("✅ websocket:v1:fusion:energy:data збережено")
        except Exception as e:
            logger.error(f"❌ process_energy error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["energy:ukrenergo:updated"],
        process_energy,
        "update_websocket_fusion_v1_energy",
        logger,
        run_once=run_once,
    )


async def update_websocket_fusion_v1_radiation(redis_client, run_once=False):
    async def process_radiation(_channel=None):
        try:
            data_cache, sensors_cache = await asyncio.gather(
                get_redis_data(logger, redis_client, "radiation:saveecobot:data:data", default_response=[]),
                get_redis_data(
                    logger,
                    redis_client,
                    "radiation:saveecobot:sensors:data",
                    default_response={"states": {}, "info": {"last_update": None}},
                ),
            )

            data = radiation.build_fusion_radiation(data_cache, sensors_cache, regions)
            corrections.apply_region_corrections(data, corrections.RADIATION_CORRECTIONS)

            logger.debug(f"⚠️ RADIATION FUSION DATA: {data}")
            logger.debug("💾 Зберігаємо websocket:v1:fusion:radiation:data")
            await set_redis_data(logger, redis_client, "websocket:v1:fusion:radiation:data", data)
            await redis_client.publish("websocket:v1:fusion:radiation:updated", "1")
            logger.info("✅ websocket:v1:fusion:radiation:data збережено")
        except Exception as e:
            logger.error(f"❌ process_radiation error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["radiation:saveecobot:updated"],
        process_radiation,
        "update_websocket_fusion_v1_radiation",
        logger,
        run_once=run_once,
    )


async def update_websocket_fusion_v1_weather_openmeteo(redis_client, run_once=False):
    async def process_weather(_channel=None):
        try:
            weather_cache = await get_redis_data(logger, redis_client, "weather:openmeteo:data", default_response=[])

            data = weather.build_fusion_weather(
                weather_cache, lambda region: region["regionId"], lambda region: region.get("temperature_2m")
            )

            logger.debug(f"⚠️ WEATHER OPENMETEO FUSION DATA: {data}")
            logger.debug("💾 Зберігаємо websocket:v1:fusion:weather_openmeteo:data")
            await set_redis_data(logger, redis_client, "websocket:v1:fusion:weather_openmeteo:data", data)
            await redis_client.publish("websocket:v1:fusion:weather_openmeteo:updated", "1")
            logger.info("✅ websocket:v1:fusion:weather_openmeteo:data збережено")
        except Exception as e:
            logger.error(f"❌ process_weather_openmeteo error: {str(e)}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

    await run_pubsub_loop(
        redis_client,
        ["weather:openmeteo:updated"],
        process_weather,
        "update_websocket_fusion_v1_weather_openmeteo",
        logger,
        run_once=run_once,
    )


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

        tasks = [
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v1_alerts, redis_client, "update_websocket_v1_alerts")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v2_alerts, redis_client, "update_websocket_v2_alerts")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v1_etryvoga, redis_client, "update_websocket_v1_etryvoga")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v2_etryvoga, redis_client, "update_websocket_v2_etryvoga")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v1_weather, redis_client, "update_websocket_v1_weather")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v1_energy, redis_client, "update_websocket_v1_energy")
            ),
            asyncio.create_task(
                run_with_restart(logger, update_websocket_v1_radiation, redis_client, "update_websocket_v1_radiation")
            ),
            asyncio.create_task(
                run_with_restart(
                    logger,
                    update_websocket_v1_global_notifications,
                    redis_client,
                    "update_websocket_v1_global_notifications",
                )
            ),
            asyncio.create_task(run_with_restart(logger, update_releases_v1, redis_client, "update_releases_v1")),
            asyncio.create_task(
                run_with_restart(
                    logger, update_websocket_fusion_v1_alerts, redis_client, "update_websocket_fusion_v1_alerts"
                )
            ),
            asyncio.create_task(
                run_with_restart(
                    logger,
                    update_websocket_fusion_v1_openweathermap,
                    redis_client,
                    "update_websocket_fusion_v1_openweathermap",
                )
            ),
            asyncio.create_task(
                run_with_restart(
                    logger, update_websocket_fusion_v1_energy, redis_client, "update_websocket_fusion_v1_energy"
                )
            ),
            asyncio.create_task(
                run_with_restart(
                    logger, update_websocket_fusion_v1_radiation, redis_client, "update_websocket_fusion_v1_radiation"
                )
            ),
            # asyncio.create_task(
            #     run_with_restart(
            #         logger, update_websocket_fusion_v1_etryvoga, redis_client, "update_websocket_fusion_v1_etryvoga"
            #     )
            # ),
            asyncio.create_task(
                run_with_restart(
                    logger, update_websocket_fusion_v2_etryvoga, redis_client, "update_websocket_fusion_v2_etryvoga"
                )
            ),
            asyncio.create_task(
                run_with_restart(
                    logger,
                    update_websocket_fusion_v1_weather_openmeteo,
                    redis_client,
                    "update_websocket_fusion_v1_weather_openmeteo",
                )
            ),
        ]

        await asyncio.gather(*tasks)

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
