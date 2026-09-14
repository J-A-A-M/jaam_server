"""
Підключення до публічного WebSocket-стріму neptun.in.ua
(https://neptun.in.ua/developers) і запис поточних загроз у Redis, за
структурою аналогічною etryvoga_ws (TYPE_CONFIG, Debouncer,
alerts:<source>:<category>:* ключі), без legacy-шару — у neptun немає
старого джерела, з яким мигрувати.

Payload-поля region/district з neptun ненадійні (перевірено на зібраних
даних: ~6% розбіжність по області, ~73% по району проти реальних
координат) — тому регіон визначається тут самостійно через
point-in-polygon по lat/lon (raions.geojson/oblasts.geojson з neptun.in.ua)
і накладається на regions.json для отримання regionId.
"""

import asyncio
import json
import logging
import os
import sys
from collections import defaultdict
from pathlib import Path

import websockets
from shapely.geometry import Point, shape

try:
    from utils import service_is_fine, set_redis_data, get_current_datetime, run_with_restart, Debouncer
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))
    from utils import service_is_fine, set_redis_data, get_current_datetime, run_with_restart, Debouncer

import redis.asyncio as redis

MODULE_DIR = Path(__file__).resolve().parent

debug_level = os.environ.get("LOGGING") or "INFO"
neptun_ws_url = os.environ.get("NEPTUN_WS_URL") or "wss://neptun.in.ua/api/v1/stream"
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
neptun_ws_debounce = float(os.environ.get("NEPTUN_WS_DEBOUNCE", 3))

logging.basicConfig(level=debug_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)


def _find_file(name):
    """Шукає файл спочатку в поточній папці (Docker: flat COPY поруч зі скриптом),
    потім в батьківській (локальний запуск з кореня репо)."""
    for candidate in (MODULE_DIR / name, MODULE_DIR.parent / name):
        if candidate.exists():
            return candidate
    return None


# Імпорт regions.json/raions.geojson/oblasts.geojson - лежать в корені репо
regions = {}
regions_path = _find_file("regions.json")
if regions_path:
    with open(regions_path, "r", encoding="utf-8") as f:
        regions = json.load(f)
else:
    logging.warning("regions.json not found, using empty regions dict")

# (data_name, ws_key) -- без legacy_key: у neptun немає старого джерела для міграції
NEPTUN_TYPE_CONFIG = {
    "uav": ("drones", "alerts:neptun_ws:drones"),
    "fpv": ("fpv", "alerts:neptun_ws:fpv"),
    "kab": ("kabs", "alerts:neptun_ws:kabs"),
    "missile": ("missiles", "alerts:neptun_ws:missiles"),
    "ballistic": ("ballistic", "alerts:neptun_ws:ballistic"),
    "recon": ("recons", "alerts:neptun_ws:recons"),
}
WS_KEY_MAP = {data_name: ws_key for data_name, ws_key in NEPTUN_TYPE_CONFIG.values()}


def _load_polys(path, name_field, name_fallback_field=None):
    data = json.loads(path.read_text(encoding="utf-8"))
    polys = []
    for feat in data["features"]:
        props = feat["properties"]
        name = props.get(name_field) or (props.get(name_fallback_field) if name_fallback_field else None)
        polys.append((name, shape(feat["geometry"])))
    return polys


raion_polys = _load_polys(_find_file("raions.geojson"), "rayon")
oblast_polys = _load_polys(_find_file("oblasts.geojson"), "region", "name")

name_to_region_id = {}
for _v in regions.values():
    name_to_region_id.setdefault(_v["name"], _v["regionId"])
name_to_region_id.setdefault("м. Київ", name_to_region_id.get("Київ"))  # аліас: oblasts.geojson != regions.json
logger.info(
    f"🗺️  Завантажено {len(raion_polys)} районів, {len(oblast_polys)} областей, {len(name_to_region_id)} назв у regions.json"
)


def resolve_region_id(lat, lon):
    """Point-in-polygon по lat/lon -> (назва для логу, regionId або None)."""
    if lat is None or lon is None:
        return None, None
    point = Point(lon, lat)
    raion_name = next((name for name, poly in raion_polys if poly.contains(point)), None)
    oblast_name = next((name for name, poly in oblast_polys if poly.contains(point)), None)

    if not raion_name and not oblast_name:
        return None, None

    display_name = raion_name or oblast_name
    region_id = name_to_region_id.get(raion_name) or name_to_region_id.get(oblast_name)
    return display_name, region_id


async def handle_threat(redis_client, threat, ws_pending, debouncer):
    """Резолвить регіон одного треку і планує запис {regionId: timestamp} у Redis."""
    threat_type = threat.get("type")
    config = NEPTUN_TYPE_CONFIG.get(threat_type)
    if not config:
        logger.debug(f"⏭️  Тип '{threat_type}' не обробляється")
        return

    data_name, ws_key = config
    display_name, region_id = resolve_region_id(threat.get("lat"), threat.get("lon"))
    if region_id is None:
        logger.warning(
            f"⚠️ Не вдалось визначити регіон: id={threat.get('id')} lat={threat.get('lat')} lon={threat.get('lon')}"
        )
        return

    ws_pending[data_name][str(region_id)] = get_current_datetime()
    await debouncer.call(lambda: flush(redis_client, ws_pending))
    logger.info(f"✅ Оновлено {display_name} (regionId={region_id}), тип: {threat_type}, id={threat.get('id')}")


async def flush(redis_client, ws_pending):
    for data_name, ws_key in WS_KEY_MAP.items():
        if ws_pending[data_name]:
            snapshot = dict(ws_pending[data_name])
            ws_pending[data_name].clear()
            await set_redis_data(logger, redis_client, f"{ws_key}:data", snapshot)
            await service_is_fine(logger, redis_client, f"{ws_key}:last_call")
            await redis_client.publish(f"{ws_key}:updated", "1")
            logger.info(f"✅ {ws_key} flushed ({len(snapshot)} регіонів)")


async def handle_frame(redis_client, raw_text, ws_pending, debouncer):
    try:
        env = json.loads(raw_text)
        env_type = env.get("type", "unknown")

        if env_type == "upsert":
            await handle_threat(redis_client, env.get("data") or {}, ws_pending, debouncer)
        elif env_type == "snapshot":
            for t in (env.get("data") or {}).get("threats", []):
                await handle_threat(redis_client, t, ws_pending, debouncer)
        elif env_type == "remove":
            logger.info(f"🗑️ remove: id={(env.get('data') or {}).get('id')}")

        await service_is_fine(logger, redis_client, "alerts:neptun_ws:last_call")
    except Exception as e:
        logger.error(f"❌ Помилка обробки фрейму: {e}")
        logger.debug("❌ Повний стек помилки:", exc_info=True)


async def connect_neptun_ws(redis_client):
    ws_pending = defaultdict(dict)
    debouncer = Debouncer(neptun_ws_debounce)

    while True:
        try:
            logger.info(f"🔌 Підключаюсь до {neptun_ws_url}")
            async with websockets.connect(neptun_ws_url) as ws:
                logger.info("✅ Підключено до neptun WebSocket")
                async for raw_text in ws:
                    await handle_frame(redis_client, raw_text, ws_pending, debouncer)
        except websockets.exceptions.ConnectionClosed as e:
            logger.warning(f"⚠️ З'єднання закрито: {e}")
        except Exception as e:
            logger.error(f"❌ Помилка з'єднання: {e}")
            logger.debug("❌ Повний стек помилки:", exc_info=True)

        logger.info("🔄 Повторне підключення через 5 секунд...")
        await asyncio.sleep(5)


async def main():
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_keepalive=True,
        health_check_interval=30,
    )

    try:
        await redis_client.ping()
        logger.info(f"✅ Successfully connected to Redis at {redis_host}:{redis_port}")

        tasks = [
            asyncio.create_task(run_with_restart(logger, connect_neptun_ws, redis_client, "connect_neptun_ws", 60)),
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
