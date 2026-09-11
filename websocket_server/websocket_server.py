import asyncio
import logging
import os
import json
import struct
import secrets
import string
import datetime
import aiohttp

from geoip2 import database, errors
from zoneinfo import ZoneInfo
from websockets import ConnectionClosedError
from websockets.asyncio.server import serve, ServerConnection, Request, Response
from http import HTTPStatus
from copy import copy

import redis.asyncio as redis
import sys
from pathlib import Path

try:
    from utils import (
        get_redis_data,
        set_redis_data,
        TYPE_ALERTS_BATCH,
        TYPE_NOTIFICATIONS_BATCH,
        TYPE_WEATHER_BATCH,
        TYPE_GRID_BATCH,
        TYPE_RADIATION_BATCH,
        TYPE_FIRMWARE_UPDATE_BETA_BATCH,
        TYPE_FIRMWARE_UPDATE_PROD_BATCH,
    )
except ImportError:
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.insert(0, str(parent_dir))

    from utils import (
        get_redis_data,
        set_redis_data,
        TYPE_ALERTS_BATCH,
        TYPE_NOTIFICATIONS_BATCH,
        TYPE_WEATHER_BATCH,
        TYPE_GRID_BATCH,
        TYPE_RADIATION_BATCH,
        TYPE_FIRMWARE_UPDATE_BETA_BATCH,
        TYPE_FIRMWARE_UPDATE_PROD_BATCH,
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


class ChipIdTimeoutException(Exception):
    pass


class FirmwareTimeoutException(Exception):
    pass


server_timezone = ZoneInfo("Europe/Kyiv")

log_level = os.environ.get("LOGGING") or "DEBUG"
websocket_port = os.environ.get("WEBSOCKET_PORT") or 38440
ping_interval = int(os.environ.get("PING_INTERVAL") or 20)
ping_timeout = int(os.environ.get("PING_TIMEOUT") or 20)
ping_timeout_count = int(os.environ.get("PING_TIMEOUT_COUNT") or 1)
redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))
environment = os.environ.get("ENVIRONMENT") or "PROD"
geo_lite_db_path = os.environ.get("GEO_PATH") or "GeoLite2-City.mmdb"
ip_info_token = os.environ.get("IP_INFO_TOKEN") or ""
geo_ip_cache_ttl = int(os.environ.get("GEO_IP_CACHE_TTL") or 86400)  # 24 hours by default
weather_source = os.environ.get("WEATHER_SOURCE") or "openmeteo"  # openweathermap or openmeteo

logging.basicConfig(level=log_level, format="%(asctime)s %(levelname)s : %(message)s")
logger = logging.getLogger(__name__)

# Налаштування джерела погоди
if weather_source == "openmeteo":
    WEATHER_DATA_KEY = "websocket:v1:fusion:weather_openmeteo:data"
    WEATHER_UPDATED_CHANNEL = "websocket:v1:fusion:weather_openmeteo:updated"
    logger.info("🌤️  Weather source: OpenMeteo")
else:
    WEATHER_DATA_KEY = "websocket:v1:fusion:openweathermap:data"
    WEATHER_UPDATED_CHANNEL = "websocket:v1:fusion:openweathermap:updated"
    logger.info("🌤️  Weather source: OpenWeatherMap")

geo = database.Reader(geo_lite_db_path)

# --- Стелі паралелізму до Redis --------------------------------------------
# Пул redis-py КИДАЄ ConnectionError, а не чекає, коли всі connection зайняті.
# Тому REDIS_MAX_CONNECTIONS мусить бути більшим за суму всіх одночасних
# споживачів + 1 на pub/sub у redis_fanout. Інваріант перевіряє
# tests/test_websocket_fanout.py — при зміні будь-якого числа він упаде.
GEO_IP_CONCURRENCY = 50
HANDSHAKE_CONCURRENCY = 32
CLIENT_SYNC_CONCURRENCY = 8
REDIS_MAX_CONNECTIONS = 150


class RedisBackedClient(dict):
    """
    Обгортка над словником клієнта, яка автоматично синхронізує зміни з Redis.
    Зберігає клієнта в Redis при кожній зміні даних.
    """

    def __init__(self, client_key: str, redis_client, initial_data: dict, ttl: int = 3600):
        super().__init__(initial_data)
        self._client_key = client_key
        self._redis_client = redis_client
        self._ttl = ttl  # Time to live in seconds (default 1 hour)
        self._sync_lock = asyncio.Lock()
        self._pending_sync = False
        self._sync_task = None
        self._last_sync_time = 0  # Timestamp останньої синхронізації
        self._min_sync_interval = 2.0  # Мінімальний інтервал між синхронізаціями (секунди)
        self._deleted = False

    async def _sync_to_redis(self):
        """Синхронізує поточний стан клієнта в Redis"""
        async with self._sync_lock:
            try:
                # Rate limiting: чекаємо залишок інтервалу замість того, щоб викинути зміну.
                # Чекаємо під локом — зміни, що прийдуть за цей час, потраплять у цей же sync.
                current_time = asyncio.get_event_loop().time()
                time_since_last_sync = current_time - self._last_sync_time
                if time_since_last_sync < self._min_sync_interval:
                    await asyncio.sleep(self._min_sync_interval - time_since_last_sync)
                    current_time = asyncio.get_event_loop().time()

                # Клієнт міг відключитись поки ми чекали — інакше запишемо його назад після DELETE
                if self._deleted:
                    return

                # Серіалізуємо дані клієнта в JSON
                client_data = {k: v for k, v in self.items()}
                # Конвертуємо байтові хеші в hex для JSON серіалізації
                # if "alerts_hash" in client_data and isinstance(client_data["alerts_hash"], (bytes, int)):
                #     if isinstance(client_data["alerts_hash"], bytes):
                #         client_data["alerts_hash"] = client_data["alerts_hash"].hex()
                #     else:
                #         client_data["alerts_hash"] = client_data["alerts_hash"]

                # Очищаємо дані від некоректних UTF-8 символів (surrogates)
                client_data = sanitize_for_json(client_data)

                redis_key = f"websocket:clients:{self._client_key}"
                async with shared_data.client_sync_semaphore:
                    await asyncio.wait_for(
                        set_redis_data(logger, self._redis_client, redis_key, client_data, expiry=self._ttl),
                        timeout=3.0,  # Таймаут 3 секунди для запису в Redis
                    )
                self._last_sync_time = current_time
                logger.debug(f"Client {self._client_key} synced to Redis")
            except asyncio.TimeoutError:
                logger.warning(f"Redis sync timeout for client {self._client_key} - operation will be retried")
            except Exception as e:
                logger.error(f"Failed to sync client {self._client_key} to Redis: {e}")

    def _schedule_sync(self):
        """Планує синхронізацію з Redis (debouncing для зменшення навантаження)"""
        if self._deleted:
            return
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(self._delayed_sync())

    async def _delayed_sync(self):
        """Затримана синхронізація для батчингу змін"""
        await asyncio.sleep(1.0)  # Збільшена затримка для кращого батчингу змін
        await self._sync_to_redis()

    def __setitem__(self, key, value):
        """Override для автоматичної синхронізації при зміні значення"""
        super().__setitem__(key, value)
        self._schedule_sync()

    def update(self, *args, **kwargs):
        """Override для автоматичної синхронізації при масовому оновленні"""
        super().update(*args, **kwargs)
        self._schedule_sync()

    async def force_sync(self):
        """Примусова синхронізація без затримки"""
        await self._sync_to_redis()

    async def delete_from_redis(self):
        """Видаляє клієнта з Redis"""
        # Спершу глушимо синхронізацію: інакше sync, що чекає у rate-limit, прокинеться
        # після DELETE і запише клієнта назад на ще 2 хвилини (TTL).
        self._deleted = True
        if self._sync_task and not self._sync_task.done():
            self._sync_task.cancel()
        try:
            redis_key = f"websocket:clients:{self._client_key}"
            async with shared_data.client_sync_semaphore:
                # Таймаут 2 секунди для видалення
                await asyncio.wait_for(self._redis_client.delete(redis_key), timeout=2.0)
            logger.debug(f"Client {self._client_key} deleted from Redis")
        except asyncio.TimeoutError:
            logger.warning(f"Redis delete timeout for client {self._client_key}")
        except Exception as e:
            logger.error(f"Failed to delete client {self._client_key} from Redis: {e}")


class SharedData:
    def __init__(self):
        # self.alerts_v1 = []
        # self.alerts_v2 = []
        # self.weather_v1 = []
        # self.explosions_v1 = []
        # self.missiles_v1 = []
        # self.missiles_v2 = []
        # self.drones_v1 = []
        # self.drones_v2 = []
        # self.kabs_v1 = []
        # self.kabs_v2 = []
        # self.energy_v1 = []
        # self.radiation_v1 = []
        # self.global_notifications_v1 = {}
        # self.alerts_fusion_actual = {}
        # self.alerts_fusion_previous = {}
        # self.notifications_fusion = {}
        # self.weather_fusion = {}
        # self.bins = []
        # self.test_bins = []
        # self.s3_bins = []
        # self.s3_test_bins = []
        # self.c3_bins = []
        # self.c3_test_bins = []
        self.clients = {}
        # channel -> набір черг клієнтів, підписаних на цей канал (fan-out від redis_fanout)
        self.subscribers: dict[str, set[asyncio.Queue]] = {}
        self.blocked_ips = []
        self.test_id = None
        self.redis_client = None
        self.http_session = None
        # Semaphore для контролю кількості одночасних Geo IP запитів (макс 50)
        # Це використовується тільки для фонових запитів, основні підключення не блокуються
        self.geo_ip_semaphore = asyncio.Semaphore(GEO_IP_CONCURRENCY)
        # Стеля паралельних handshake-читань. Має лишатись нижчою за max_connections пулу,
        # інакше при масовому реконекті пул кидає ConnectionError("Too many connections").
        self.handshake_semaphore = asyncio.Semaphore(HANDSHAKE_CONCURRENCY)
        # Запис/видалення websocket:clients:*. Кожен legacy fan-out пише в client[field],
        # що планує sync у ~60 клієнтів одночасно — без стелі це вичерпує пул.
        self.client_sync_semaphore = asyncio.Semaphore(CLIENT_SYNC_CONCURRENCY)

    def subscribe(self, queue: asyncio.Queue, channels):
        for channel in channels:
            self.subscribers.setdefault(channel, set()).add(queue)

    def unsubscribe(self, queue: asyncio.Queue, channels):
        for channel in channels:
            self.subscribers.get(channel, set()).discard(queue)


shared_data = SharedData()


class AlertVersion:
    v1 = 1
    v2 = 2
    v3 = 3
    v4 = 4
    v5 = 5


# --- Канали pub/sub ---------------------------------------------------------
# Набір каналів однаковий для всіх клієнтів однієї версії, тому підписка одна
# на процес (redis_fanout), а не одна на клієнта.

FUSION_CHANNELS = [
    "websocket:v1:fusion:alerts:updated",
    WEATHER_UPDATED_CHANNEL,
    "websocket:v1:fusion:energy:updated",
    "websocket:v1:fusion:radiation:updated",
    "websocket:v1:fusion:etryvoga:updated",
    "releases:production:updated",
    "releases:beta:updated",
]

LEGACY_WEATHER_CHANNEL = "websocket:v1:legacy:weather:updated"
LEGACY_BINS_CHANNEL = "releases:production:updated"
LEGACY_TEST_BINS_CHANNEL = "releases:beta:updated"

# channel -> (redis_key, client_field, payload_name, payload_data_key, transform)
_LEGACY_ALERTS_V1 = {
    "websocket:v1:legacy:alerts:updated": ("websocket:v1:legacy:alerts", "alerts", "alerts", "alerts", None),
}
_LEGACY_ALERTS_V2 = {
    "websocket:v2:legacy:alerts:updated": ("websocket:v2:legacy:alerts", "alerts", "alerts", "alerts", None),
}
_LEGACY_EXPLOSIONS = {
    "websocket:v1:legacy:explosions:updated": (
        "websocket:v1:legacy:explosions",
        "explosions",
        "explosions",
        "explosions",
        "int_list",
    ),
}
_LEGACY_V3_EXTRA = {
    "websocket:v1:legacy:missiles:updated": (
        "websocket:v1:legacy:missiles",
        "missiles",
        "missiles",
        "missiles",
        "int_list",
    ),
    "websocket:v1:legacy:drones:updated": (
        "websocket:v1:legacy:drones",
        "drones",
        "drones",
        "drones",
        "int_list",
    ),
}
_LEGACY_V4_EXTRA = {
    "websocket:v2:legacy:missiles:updated": (
        "websocket:v2:legacy:missiles",
        "missiles2",
        "missiles2",
        "missiles",
        None,
    ),
    "websocket:v2:legacy:drones:updated": ("websocket:v2:legacy:drones", "drones2", "drones2", "drones", None),
    "websocket:v1:legacy:kabs:updated": ("websocket:v1:legacy:kabs", "kabs", "kabs", "kabs", None),
    "websocket:v2:legacy:kabs:updated": ("websocket:v2:legacy:kabs", "kabs2", "kabs2", "kabs", None),
    "websocket:v1:legacy:energy:updated": ("websocket:v1:legacy:energy", "energy", "energy", "energy", None),
    "websocket:v1:legacy:radiation:updated": (
        "websocket:v1:legacy:radiation",
        "radiation",
        "radiation",
        "radiation",
        None,
    ),
    "websocket:v1:legacy:global_notifications:updated": (
        "websocket:v1:legacy:global_notifications",
        "global_notifications",
        "global_notifications",
        "global_notifications",
        None,
    ),
}

LEGACY_VERSION_CHANNELS = {
    AlertVersion.v1: _LEGACY_ALERTS_V1,
    AlertVersion.v2: {**_LEGACY_EXPLOSIONS, **_LEGACY_ALERTS_V2},
    AlertVersion.v3: {**_LEGACY_EXPLOSIONS, **_LEGACY_ALERTS_V2, **_LEGACY_V3_EXTRA},
    AlertVersion.v4: {**_LEGACY_EXPLOSIONS, **_LEGACY_ALERTS_V2, **_LEGACY_V3_EXTRA, **_LEGACY_V4_EXTRA},
}


def legacy_channels(alert_version) -> list[str]:
    version_channels = LEGACY_VERSION_CHANNELS.get(alert_version, {})
    return list(version_channels) + [LEGACY_WEATHER_CHANNEL, LEGACY_BINS_CHANNEL, LEGACY_TEST_BINS_CHANNEL]


# Union усіх версій: v1 слухає v1-канал алертів, v2+ — v2-канал, тож v4 сам по собі не покриває все
ALL_CHANNELS = sorted({*FUSION_CHANNELS, *(ch for v in LEGACY_VERSION_CHANNELS for ch in legacy_channels(v))})

# Канали, чий redis_key не виводиться як channel.removesuffix(":updated")
_CHANNEL_KEY_OVERRIDES = {
    "websocket:v1:fusion:alerts:updated": "websocket:v1:fusion:payload:alerts",
    "websocket:v1:fusion:etryvoga:updated": "websocket:v1:fusion:payload:notifications",
    "websocket:v1:fusion:energy:updated": "websocket:v1:fusion:energy:data",
    "websocket:v1:fusion:radiation:updated": "websocket:v1:fusion:radiation:data",
    WEATHER_UPDATED_CHANNEL: WEATHER_DATA_KEY,
}
# Готовий бінарний payload у вигляді hex-рядка
_HEX_PAYLOAD_CHANNELS = {
    "websocket:v1:fusion:alerts:updated",
    "websocket:v1:fusion:etryvoga:updated",
}
# Словник стану {region_id: value}
_DICT_STATE_CHANNELS = {
    WEATHER_UPDATED_CHANNEL,
    "websocket:v1:fusion:energy:updated",
    "websocket:v1:fusion:radiation:updated",
}


def channel_source(channel: str) -> tuple[str, object]:
    """(redis_key, default_response) для каналу."""
    key = _CHANNEL_KEY_OVERRIDES.get(channel) or channel.removesuffix(":updated")
    if channel in _HEX_PAYLOAD_CHANNELS:
        return key, ""
    if channel in _DICT_STATE_CHANNELS:
        return key, {}
    return key, []


def bin_sort(bin):
    if bin.startswith("latest"):
        return (100, 0, 0, 0)
    version = bin.removesuffix(".bin")
    fw_beta = version.split("-")
    fw = fw_beta[0]
    if len(fw_beta) == 1:
        beta = 10000
    else:
        beta = int(fw_beta[1].removeprefix("b"))

    major_minor_patch = fw.split(".")
    major = int(major_minor_patch[0])
    if len(major_minor_patch) == 1:
        minor = 0
        patch = 0
    elif len(major_minor_patch) == 2:
        minor = int(major_minor_patch[1])
        patch = 0
    else:
        minor = int(major_minor_patch[1])
        patch = int(major_minor_patch[2])

    return (major, minor, patch, beta)


def sanitize_for_json(obj):
    """
    Очищає об'єкт від некоректних символів для JSON серіалізації.
    Видаляє surrogate pairs та інші проблемні символи.
    """
    if isinstance(obj, str):
        # Видаляємо surrogate pairs та інші некоректні символи
        return obj.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
    elif isinstance(obj, dict):
        return {sanitize_for_json(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return type(obj)(sanitize_for_json(item) for item in obj)
    elif isinstance(obj, (int, float, bool, type(None))):
        return obj
    else:
        # Для інших типів спробуємо конвертувати в строку та очистити
        return str(obj).encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")


def generate_random_hash(length):
    characters = string.ascii_lowercase + string.digits  # a-z, 0-9
    return "".join(secrets.choice(characters) for _ in range(length))


async def create_redis_backed_client(
    client_key: str, redis_client, initial_data: dict, ttl: int = 3600
) -> RedisBackedClient:
    """
    Створює нового клієнта з автоматичною синхронізацією в Redis.

    Args:
        client_key: Унікальний ключ клієнта (наприклад, "{ip}_{id}")
        redis_client: Redis клієнт для синхронізації
        initial_data: Початкові дані клієнта
        ttl: Час життя запису в Redis (в секундах)

    Returns:
        RedisBackedClient: Клієнт з автоматичною синхронізацією
    """
    client = RedisBackedClient(client_key, redis_client, initial_data, ttl)
    # НЕ зберігаємо початковий стан одразу - це відбудеться автоматично при першій зміні
    # або через 1 секунду через механізм _delayed_sync. Це зменшує навантаження на Redis
    # при одночасному підключенні багатьох клієнтів.
    return client


async def load_client_from_redis(client_key: str, redis_client) -> dict | None:
    """
    Завантажує дані клієнта з Redis, якщо вони існують.

    Args:
        client_key: Унікальний ключ клієнта
        redis_client: Redis клієнт

    Returns:
        dict | None: Дані клієнта або None, якщо клієнт не знайдено
    """
    try:
        redis_key = f"websocket:clients:{client_key}"
        data = await get_redis_data(logger, redis_client, redis_key)
        if data:
            client_data = json.loads(data)
            # Конвертуємо hex хеш назад в int
            # if "alerts_hash" in client_data and isinstance(client_data["alerts_hash"], str):
            #     try:
            #         client_data["alerts_hash"] = int(client_data["alerts_hash"], 16)
            #     except (ValueError, TypeError):
            #         client_data["alerts_hash"] = 0
            return client_data
        return None
    except Exception as e:
        logger.error(f"Failed to load client {client_key} from Redis: {e}")
        return None


def get_chip_id(client, client_id):
    return client["chip_id"] if client["chip_id"] != "unknown" else client_id


async def get_client_chip_id(client, chip_id_event):
    try:
        await asyncio.wait_for(chip_id_event.wait(), timeout=10.0)
        return client["chip_id"]
    except asyncio.TimeoutError:
        raise ChipIdTimeoutException("Chip ID timeout")


async def get_client_firmware(client, firmware_event):
    try:
        await asyncio.wait_for(firmware_event.wait(), timeout=10.0)
        return client["firmware"]
    except asyncio.TimeoutError:
        raise FirmwareTimeoutException("Firmware timeout")


async def get_client_ip(connection: ServerConnection):
    return connection.request.headers.get(
        "CF-Connecting-IP", connection.request.headers.get("X-Real-IP", connection.remote_address[0])
    )


async def get_geo_ip_data_cached_or_default(ip, request, client_key=None):
    """
    Швидкий запит Geo IP даних: спочатку перевіряє Redis cache, потім дає дефолтні дані
    та запускає асинхронне оновлення на фоні (без блокування підключення).
    Це дозволяє майже миттєво підключити клієнта, незалежно від стану ipinfo.io
    """
    redis_client = shared_data.redis_client
    cache_key = f"geo_ip:{ip}"

    # Спробуємо прочитати з Redis cache (дуже швидко, ~1-10ms)
    if redis_client:
        try:
            cached_data = await asyncio.wait_for(
                redis_client.hgetall(cache_key), timeout=0.5  # Коротка затримка для читання з кешу
            )
            if cached_data:
                logger.debug(f"{ip} >>> Geo data from Redis cache")
                return dict(cached_data)
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"{ip} >>> Cache miss or timeout, using defaults: {e}")

    # Дефолтні дані з Cloudflare headers та локальної інформації
    data = _get_geo_ip_defaults(ip, request)

    # Запускаємо асинхронне оновлення на фоні (без очікування)
    if redis_client:
        asyncio.create_task(_fetch_and_cache_geo_ip(ip, request, cache_key, redis_client, client_key))

    return data


def _get_geo_ip_defaults(ip, request):
    """Отримує дефолтні Geo IP дані з Cloudflare headers та GeoLite2"""
    try:
        country = request.headers.get("cf-ipcountry", "unknown")
        region = request.headers.get("cf-region", "unknown")
        city = request.headers.get("cf-ipcity", "unknown")
        timezone = request.headers.get("cf-timezone", "UTC")
        longitude = request.headers.get("cf-iplongitude", "0")
        latitude = request.headers.get("cf-iplatitude", "0")
        postal_code = request.headers.get("cf-postal-code", "unknown")

        # Якщо Cloudflare дані не повні, використовуємо GeoLite2
        if not all([country, region, city, timezone]):
            try:
                response = geo.city(ip)
                city = city or response.city.name or "unknown"
                region = region or response.subdivisions.most_specific.name or "unknown"
                country = country or response.country.iso_code or "unknown"
                timezone = timezone or response.location.time_zone or "UTC"
                latitude = latitude or str(response.location.latitude) or "0"
                longitude = longitude or str(response.location.longitude) or "0"
                postal_code = postal_code or response.postal.code or "unknown"
            except Exception:
                pass  # Якщо GeoLite2 теж не вдалося, залишаємо дефолтні

        data = {
            "hostname": "unknown",
            "city": str(city),
            "region": str(region),
            "country": str(country),
            "loc": f"{latitude},{longitude}",
            "org": "unknown",
            "postal": str(postal_code),
            "timezone": str(timezone),
        }
        # Очищаємо дані від некоректних символів
        return sanitize_for_json(data)
    except Exception as e:
        logger.warning(f"Error getting geo defaults for {ip}: {e}")
        return {
            "hostname": "unknown",
            "city": "unknown",
            "region": "unknown",
            "country": "unknown",
            "loc": "0,0",
            "org": "unknown",
            "postal": "unknown",
            "timezone": "UTC",
        }


async def _fetch_and_cache_geo_ip(ip, request, cache_key, redis_client, client_key=None):
    """
    Асинхронне завдання для отримання Geo IP даних з ipinfo.io та кешування в Redis.
    Запускається на фоні без блокування підключення клієнта.
    Також оновлює дані в активному клієнту, якщо він ще підключений.
    """
    try:
        async with shared_data.geo_ip_semaphore:
            data = await _fetch_geo_ip_data_from_sources(ip, request)

            # Кешуємо в Redis
            try:
                await asyncio.wait_for(redis_client.hset(cache_key, mapping=data), timeout=2.0)
                await asyncio.wait_for(redis_client.expire(cache_key, geo_ip_cache_ttl), timeout=1.0)
                logger.debug(f"{ip} >>> Geo data cached in Redis")
            except asyncio.TimeoutError:
                logger.warning(f"⚠️ Redis cache write timeout for {ip}")
            except Exception as e:
                logger.warning(f"⚠️ Error caching geo data for {ip}: {e}")

            # Оновлюємо дані у активного клієнта (якщо він ще підключений)
            if client_key and client_key in shared_data.clients:
                try:
                    client = shared_data.clients[client_key]
                    if isinstance(client, RedisBackedClient):
                        # Оновлюємо дані в клієнті
                        client["city"] = data.get("city", client.get("city", "unknown"))
                        client["region"] = data.get("region", client.get("region", "unknown"))
                        client["country"] = data.get("country", client.get("country", "unknown"))
                        client["timezone"] = data.get("timezone", client.get("timezone", "UTC"))
                        client["org"] = data.get("org", client.get("org", "unknown"))
                        client["location"] = data.get("loc", client.get("location", "0,0"))
                        logger.debug(f"{ip} >>> Updated client {client_key} with fresh geo data")
                except Exception as e:
                    logger.warning(f"⚠️ Error updating client {client_key} with geo data: {e}")
    except Exception as e:
        logger.warning(f"⚠️ Background geo fetch failed for {ip}: {e}")


async def get_geo_ip_data(ip, request):
    redis_client = shared_data.redis_client
    if not redis_client:
        logger.error("Redis client not initialized in get_geo_ip_data")
        async with shared_data.geo_ip_semaphore:
            return await _fetch_geo_ip_data_from_sources(ip, request)

    cache_key = f"geo_ip:{ip}"
    try:
        cached_data = await asyncio.wait_for(
            redis_client.hgetall(cache_key), timeout=3.0  # Таймаут 3 секунди для читання з кешу
        )
        if cached_data:
            ttl = await asyncio.wait_for(redis_client.ttl(cache_key), timeout=2.0)
            logger.debug(f"{ip} >>> data from Redis hash cache (TTL: {ttl}s remaining)")
            return dict(cached_data)
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ Redis cache read timeout for {ip} - fetching from source")
    except Exception as e:
        logger.warning(f"⚠️ Error reading from Redis hash cache: {e}")

    # Використовуємо semaphore для контролю паралельних запитів
    async with shared_data.geo_ip_semaphore:
        data = await _fetch_geo_ip_data_from_sources(ip, request)

    try:
        await asyncio.wait_for(
            redis_client.hset(cache_key, mapping=data), timeout=3.0  # Таймаут 3 секунди для запису в кеш
        )
        await asyncio.wait_for(redis_client.expire(cache_key, geo_ip_cache_ttl), timeout=2.0)
        logger.debug(f"{ip} >>> data cached in Redis hash with automatic TTL {geo_ip_cache_ttl}s")
    except asyncio.TimeoutError:
        logger.warning(f"⚠️ Redis cache write timeout for {ip} - continuing without cache")
    except Exception as e:
        logger.warning(f"⚠️ Error saving to Redis hash cache: {e}")

    return data


def _get_geo_ip_fallback(ip, request):
    """Fallback до Cloudflare headers та GeoLite2 коли ipinfo.io недоступний"""
    country = request.headers.get("cf-ipcountry", None)
    region = request.headers.get("cf-region", None)
    city = request.headers.get("cf-ipcity", None)
    timezone = request.headers.get("cf-timezone", None)
    longitude = request.headers.get("cf-iplongitude", None)
    latitude = request.headers.get("cf-iplatitude", None)
    postal_code = request.headers.get("cf-postal-code", None)

    if not country or not region or not city or not timezone:
        try:
            geo_response = geo.city(ip)
            city = city or geo_response.city.name or "not-in-db"
            region = region or geo_response.subdivisions.most_specific.name or "not-in-db"
            country = country or geo_response.country.iso_code or "not-in-db"
            timezone = timezone or geo_response.location.time_zone or "not-in-db"
            latitude = latitude or geo_response.location.latitude or 0
            longitude = longitude or geo_response.location.longitude or 0
            postal_code = postal_code or geo_response.postal.code or "not-in-db"
        except errors.AddressNotFoundError:
            city = city or "not-found"
            region = region or "not-found"
            country = country or "not-found"
            timezone = timezone or "not-found"
            latitude = latitude or 0
            longitude = longitude or 0
            postal_code = postal_code or "not-found"

    data = {
        "hostname": "unknown",
        "city": str(city),
        "region": str(region),
        "country": str(country),
        "loc": f"{latitude},{longitude}",
        "org": "unknown",
        "postal": str(postal_code),
        "timezone": str(timezone),
    }
    data = sanitize_for_json(data)
    logger.debug(f"{ip} >>> data from headers/GeoLite2: {data}")
    return data


async def _fetch_geo_ip_data_from_sources(ip, request):
    try:
        session = shared_data.http_session
        async with asyncio.timeout(3.0):
            async with session.get(f"https://ipinfo.io/{ip}?token={ip_info_token}") as response:
                data = await response.json()
                data["org"] = data["org"].split(" ", 1)[1] if data["org"].startswith("AS") else data["org"]
                data = sanitize_for_json(data)
                logger.debug(f"{ip} >>> data from IPINFO: {data}")
                return data
    except asyncio.TimeoutError:
        logger.warning(f"ipinfo.io request timeout for {ip} - using fallback")
    except Exception as e:
        logger.warning(f"Error fetching from ipinfo.io: {e}")

    return _get_geo_ip_fallback(ip, request)


async def message_handler(
    websocket: ServerConnection, client, client_id, client_ip, country, region, city, chip_id_event, firmware_event
):
    async for message in websocket:
        try:
            chip_id = get_chip_id(client, client_id)

            logger.debug(f"{client_ip}:{chip_id} >>> {message}")

            def split_message(message):
                parts = message.split(":", 1)  # Split at most into 2 parts
                header = parts[0]
                data = parts[1] if len(parts) > 1 else ""
                return header, data

            header, data = split_message(message)
            match header:
                case "firmware":
                    client["firmware"] = data
                    firmware_event.set()
                    logger.debug(f"{client_ip}:{chip_id} >>> firmware saved")
                case "chip_id":
                    client["chip_id"] = data
                    chip_id_event.set()
                    logger.debug(f"{client_ip}:{chip_id} >>> chip init: {data}")
                    logger.debug(f"{client_ip}:{data} >>> chip_id saved")
                case _:
                    logger.debug(f"{client_ip}:{chip_id} !!! unknown data request {message}")
        except Exception as e:
            logger.error(f"{client_ip}:{client_id} !!! message_handler Exception - {e}")
            break


def calc_body_alerts_hash(body_alerts: bytes) -> int:
    """
    Обчислює простий 16-бітний хеш для body_alerts.
    """
    return sum(body_alerts) % 0x10000  # 65536


def find_empty_regions(old_state, new_state):
    """
    Повертає список регіонів, які відсутні в новому стані, але присутні в старому.
    """
    empty_region_ids = []
    for region_id in old_state.keys():
        if region_id not in new_state:
            empty_region_ids.append(region_id)
    return empty_region_ids


def find_changed_regions(old_state, new_state):
    """
    Оновлює стан alerts_batch_state, повертає діф (region_ids, де flags16 змінився).
    """
    diff_region_ids = []
    for region_id, flags16 in new_state.items():
        prev_flags = old_state.get(region_id)
        if prev_flags != flags16:
            diff_region_ids.append(region_id)
    return diff_region_ids


async def redis_fanout(shared_data: SharedData):
    """
    Один pub/sub connection на процес замість одного на клієнта.
    На кожну подію читає ключ рівно раз і роздає дані по чергах підписників.
    """
    pubsub = None
    while True:
        try:
            pubsub = shared_data.redis_client.pubsub()
            await pubsub.subscribe(*ALL_CHANNELS)
            logger.info(f"📡 shared pub/sub: підписано на {len(ALL_CHANNELS)} каналів")

            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message or message["type"] != "message":
                    continue

                channel = message["channel"]
                if isinstance(channel, bytes):
                    channel = channel.decode("utf-8")

                queues = shared_data.subscribers.get(channel)
                if not queues:
                    continue

                key, default = channel_source(channel)
                data = await get_redis_data(logger, shared_data.redis_client, key, default_response=default)
                logger.info(f"📬 fan-out {channel} -> {len(queues)} клієнтів")

                for queue in list(queues):
                    # drop-oldest: повільний клієнт не стопорить решту і не роздуває пам'ять
                    if queue.full():
                        try:
                            queue.get_nowait()
                        except asyncio.QueueEmpty:
                            pass
                    try:
                        queue.put_nowait((channel, data))
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning(f"shared pub/sub !!! {e}, reconnecting in 5s...")
        finally:
            if pubsub:
                try:
                    await pubsub.aclose()
                except Exception:
                    pass
                pubsub = None
        await asyncio.sleep(5)


async def alerts_data_fusion(
    websocket: ServerConnection,
    client,
    client_id,
    client_ip,
    shared_data: SharedData,
    alert_version,
    chip_id_event=None,
    firmware_event=None,
):
    queue = None
    try:
        chip_id = await get_client_chip_id(client, chip_id_event)
        firmware = await get_client_firmware(client, firmware_event)
        redis_client = shared_data.redis_client

        # Підписуємось ДО initial read: дублікат пакета нешкідливий, втрачена подія — ні.
        queue = asyncio.Queue(maxsize=32)
        shared_data.subscribe(queue, FUSION_CHANNELS)

        logger.debug(f"{client_ip}:{chip_id}: check")
        match alert_version:
            case AlertVersion.v1:
                # Послідовно, не gather: 8 паралельних читань = 8 одночасних Redis-конекшнів
                # на клієнта, що при масовому реконекті і давало пік у пулі.
                # ponytail: 16 RTT (~3 мс на bridge). Якщо стане вузьким — pipeline,
                # але тоді треба явно знати тип кожного ключа (set_redis_data пише dict як Hash).
                async with shared_data.handshake_semaphore:
                    alerts_cache = await get_redis_data(
                        logger, redis_client, "websocket:v1:fusion:alerts:data", default_response=False
                    )
                    alerts_hash_actual = await get_redis_data(
                        logger, redis_client, "websocket:v1:fusion:alerts:hash_actual", default_response=0
                    )
                    alerts_hash_previous = await get_redis_data(
                        logger, redis_client, "websocket:v1:fusion:alerts:hash_previous", default_response=0
                    )
                    weather_cache = await get_redis_data(logger, redis_client, WEATHER_DATA_KEY, default_response={})
                    energy_cache = await get_redis_data(
                        logger, redis_client, "websocket:v1:fusion:energy:data", default_response={}
                    )
                    radiation_cache = await get_redis_data(
                        logger, redis_client, "websocket:v1:fusion:radiation:data", default_response={}
                    )
                    releases_beta = await get_redis_data(logger, redis_client, "releases:beta", default_response=[])
                    releases_prod = await get_redis_data(
                        logger, redis_client, "releases:production", default_response=[]
                    )

                if alerts_cache:
                    alerts_header = struct.pack("<B", TYPE_ALERTS_BATCH)
                    alerts = bytearray()
                    for rid, flags16 in alerts_cache.items():
                        alerts += struct.pack("<H H", int(rid), flags16)
                    hash_actual = struct.pack("<H", alerts_hash_actual)
                    hash_previous = struct.pack("<H", alerts_hash_previous)
                    alerts_payload = alerts_header + hash_actual + hash_previous + alerts
                    await websocket.send(alerts_payload)
                    logger.debug(f"{client_ip}:{chip_id} <<< initial alert packet")

                if weather_cache:
                    weather_header = struct.pack("<B", TYPE_WEATHER_BATCH)
                    weather = bytearray()
                    for rid, flags8 in weather_cache.items():
                        weather += struct.pack("<H B", int(rid), int(flags8) & 0xFF)
                    weather_payload = weather_header + weather
                    await websocket.send(weather_payload)
                    logger.debug(f"{client_ip}:{chip_id} <<< initial weather packet")

                if energy_cache:
                    energy_header = struct.pack("<B", TYPE_GRID_BATCH)
                    energy_payload = energy_header + make_grid_batch(energy_cache)
                    await websocket.send(energy_payload)
                    logger.debug(f"{client_ip}:{chip_id} <<< initial energy packet")

                if radiation_cache:
                    radiation_header = struct.pack("<B", TYPE_RADIATION_BATCH)
                    radiation_payload = radiation_header + make_radiation_batch(radiation_cache)
                    await websocket.send(radiation_payload)
                    logger.debug(f"{client_ip}:{chip_id} <<< initial radiation packet")

                if releases_beta:
                    firmware_payload = make_firmware_batch(releases_beta, TYPE_FIRMWARE_UPDATE_BETA_BATCH)
                    await websocket.send(firmware_payload)
                    logger.debug(
                        f"{client_ip}:{chip_id} <<< initial firmware packet ({len(releases_beta)} beta versions)"
                    )

                if releases_prod:
                    firmware_payload = make_firmware_batch(releases_prod, TYPE_FIRMWARE_UPDATE_PROD_BATCH)
                    await websocket.send(firmware_payload)
                    logger.debug(
                        f"{client_ip}:{chip_id} <<< initial firmware packet ({len(releases_prod)} production versions)"
                    )

                client["initial"] = False

                # Дані вже прочитані спільним redis_fanout — тут лише формування пакета і send
                while True:
                    channel, data = await queue.get()
                    logger.debug(f"📬 {client_ip}:{chip_id} подія з каналу: {channel}")

                    match channel:
                        case "websocket:v1:fusion:alerts:updated":
                            payload = hex_payload(data, "websocket:v1:fusion:payload:alerts", client_ip, chip_id)
                            if payload is False:
                                continue
                            await websocket.send(payload)
                            logger.debug(f"{client_ip}:{chip_id} <<< new alert packet")
                        case channel if channel == WEATHER_UPDATED_CHANNEL:
                            payload = struct.pack("<B", TYPE_WEATHER_BATCH) + make_weather_batch(data)
                            await websocket.send(payload)
                            logger.debug(f"{client_ip}:{chip_id} <<< new weather packet")
                        case "websocket:v1:fusion:energy:updated":
                            payload = struct.pack("<B", TYPE_GRID_BATCH) + make_grid_batch(data)
                            await websocket.send(payload)
                            logger.debug(f"{client_ip}:{chip_id} <<< new energy packet")
                        case "websocket:v1:fusion:radiation:updated":
                            payload = struct.pack("<B", TYPE_RADIATION_BATCH) + make_radiation_batch(data)
                            await websocket.send(payload)
                            logger.debug(f"{client_ip}:{chip_id} <<< new radiation packet")
                        case "websocket:v1:fusion:etryvoga:updated":
                            payload = hex_payload(data, "websocket:v1:fusion:payload:notifications", client_ip, chip_id)
                            if payload is False:
                                continue
                            await websocket.send(payload)
                            logger.debug(f"{client_ip}:{chip_id} <<< new notifications packet")
                        case "releases:production:updated":
                            await websocket.send(make_firmware_batch(data, TYPE_FIRMWARE_UPDATE_PROD_BATCH))
                            logger.debug(
                                f"{client_ip}:{chip_id} <<< updated firmware packet ({len(data)} prod versions)"
                            )
                        case "releases:beta:updated":
                            await websocket.send(make_firmware_batch(data, TYPE_FIRMWARE_UPDATE_BETA_BATCH))
                            logger.debug(
                                f"{client_ip}:{chip_id} <<< updated firmware packet ({len(data)} beta versions)"
                            )
                        case _:
                            logger.warning(f"{client_ip}:{chip_id} !!! Невідомий канал: {channel}")

    except asyncio.CancelledError as e:
        logger.debug(f"{client_ip}:{client_id} !!! alerts_data_fusion cancelled - {e}")
    except ChipIdTimeoutException as e:
        logger.debug(f"{client_ip}:{client_id} !!! chip_id timeout, closing connection - {e}")
    except FirmwareTimeoutException as e:
        logger.debug(f"{client_ip}:{client_id} !!! firmware timeout, closing connection - {e}")
    except Exception as e:
        logger.debug(f"{client_ip}:{client_id} !!! alerts_data_fusion Exception - {e}", exc_info=True)
    finally:
        if queue is not None:
            shared_data.unsubscribe(queue, FUSION_CHANNELS)


async def alerts_data(
    websocket: ServerConnection,
    client,
    client_id,
    client_ip,
    shared_data: SharedData,
    alert_version,
    chip_id_event=None,
    firmware_event=None,
):
    queue = None
    channels = []
    try:
        chip_id = await get_client_chip_id(client, chip_id_event)
        firmware = await get_client_firmware(client, firmware_event)
        redis_client = shared_data.redis_client

        version_channels = LEGACY_VERSION_CHANNELS.get(alert_version, {})
        channels = legacy_channels(alert_version)
        bins_are_dicts = True  # bins — це список dict з полем "tag"

        # Підписуємось ДО initial read: дублікат пакета нешкідливий, втрачена подія — ні.
        queue = asyncio.Queue(maxsize=32)
        shared_data.subscribe(queue, channels)

        async def send_data_channel(data, client_field, payload_name, payload_data_key, transform):
            if client[client_field] != data:
                if transform == "int_list":
                    formatted = json.dumps([int(x) for x in data])
                elif transform == "float_list":
                    formatted = json.dumps([float(x) for x in data])
                else:
                    formatted = data
                ws_payload = '{"payload": "%s", "%s": %s}' % (payload_name, payload_data_key, formatted)
                await websocket.send(ws_payload)
                logger.debug(f"{client_ip}:{chip_id} <<< new {payload_name}")
                client[client_field] = data

        async def send_weather(data):
            if client["weather"] != data:
                weather = json.dumps([float(w) for w in data])
                ws_payload = '{"payload":"weather","weather":%s}' % weather
                await websocket.send(ws_payload)
                logger.debug(f"{client_ip}:{chip_id} <<< new weather")
                client["weather"] = data

        async def send_bins(data, client_field, payload_name, are_dicts):
            if client[client_field] != data:
                if are_dicts:
                    seen = set()
                    temp_bins = []
                    for b in data:
                        if b["tag"] in seen:
                            continue
                        seen.add(b["tag"])
                        temp_bins.append(f'{b["tag"]}.bin')
                else:
                    temp_bins = list(data)
                temp_bins.sort(key=bin_sort, reverse=True)
                ws_payload = '{"payload": "%s", "%s": %s}' % (payload_name, payload_name, temp_bins)
                await websocket.send(ws_payload)
                logger.debug(f"{client_ip}:{chip_id} <<< new {payload_name}")
                client[client_field] = data

        async def dispatch(channel, data):
            if channel in version_channels:
                _, client_field, payload_name, payload_data_key, transform = version_channels[channel]
                await send_data_channel(data, client_field, payload_name, payload_data_key, transform)
            elif channel == LEGACY_WEATHER_CHANNEL:
                await send_weather(data)
            elif channel == LEGACY_BINS_CHANNEL:
                await send_bins(data, "bins", "bins", bins_are_dicts)
            elif channel == LEGACY_TEST_BINS_CHANNEL:
                await send_bins(data, "test_bins", "test_bins", bins_are_dicts)
            else:
                logger.warning(f"{client_ip}:{chip_id} !!! unknown legacy channel: {channel}")

        # Початкові дані читає сам клієнт: dedup-гейт (client[field] != data) залежить від його стану
        async with shared_data.handshake_semaphore:
            for channel in channels:
                key, default = channel_source(channel)
                await dispatch(channel, await get_redis_data(logger, redis_client, key, default_response=default))

        logger.debug(f"{client_ip}:{chip_id} <<< initial legacy data sent")

        # Дані вже прочитані спільним redis_fanout — тут лише dedup і send
        while True:
            channel, data = await queue.get()
            logger.debug(f"📬 {client_ip}:{chip_id} подія з каналу: {channel}")
            await dispatch(channel, data)

    except asyncio.CancelledError as e:
        logger.debug(f"{client_ip}:{client_id} !!! alerts_data cancelled - {e}")
    except ChipIdTimeoutException as e:
        logger.debug(f"{client_ip}:{client_id} !!! chip_id timeout, closing connection - {e}")
    except FirmwareTimeoutException as e:
        logger.debug(f"{client_ip}:{client_id} !!! firmware timeout, closing connection - {e}")
    except Exception as e:
        logger.debug(f"{client_ip}:{client_id} !!! alerts_data Exception - {e}", exc_info=True)
    finally:
        if queue is not None:
            shared_data.unsubscribe(queue, channels)


async def ping_pong(websocket: ServerConnection, client, client_id, client_ip):
    timeouts_count = 0
    while True:
        chip_id = get_chip_id(client, client_id)
        try:
            payload = (timeouts_count + 1).to_bytes(1, "big")
            pong_waiter = await websocket.ping(payload)
            logger.debug(f"{client_ip}:{chip_id} >>> ping with payload: {payload.hex()} (binary)")
            latency = await asyncio.wait_for(asyncio.shield(pong_waiter), ping_timeout)
            logger.debug(f"{client_ip}:{chip_id} <<< pong, latency: {latency}")
            client["latency"] = int(latency * 1000)  # convert to ms
            timeouts_count = 0
            await asyncio.sleep(ping_interval)
        except asyncio.TimeoutError:
            timeouts_count += 1
            if timeouts_count < ping_timeout_count:
                logger.debug(f"{client_ip}:{chip_id} !!! pong timeout {timeouts_count}, retrying")
                continue
            logger.debug(f"{client_ip}:{chip_id} !!! pong timeout, closing connection")
            break
        except ConnectionClosedError as e:
            logger.debug(f"{client_ip}:{chip_id} !!! ping_pong connection closed - {e}")
            break
        except Exception as e:
            logger.debug(f"{client_ip}:{chip_id} !!! ping_pong Exception - {e}", exc_info=True)
            break


async def echo(websocket: ServerConnection):
    client = None
    try:
        client_id = generate_random_hash(8)
        # get real header from websocket
        client_ip = await get_client_ip(websocket)
        secure_connection = websocket.request.headers.get("X-Connection-Secure", "false")
        logger.info(f"{client_ip}:{client_id} >>> new client")

        if client_ip in shared_data.blocked_ips:
            logger.warning(f"{client_ip}:{client_id} !!! BLOCKED")
            return

        client_key = f"{client_ip}:{client_id}"

        # Швидке отримання Geo IP даних без блокування (дефолтні дані + фоновий запит)
        geo_ip_data = await get_geo_ip_data_cached_or_default(client_ip, websocket.request, client_key)

        # if response.country.iso_code != 'UA' and response.continent.code != 'EU':
        #     shared_data.blocked_ips.append(client_ip)
        #     logger.warning(f"{client_ip}_{client_port} !!! BLOCKED")
        #     return

        # Створюємо нового клієнта (при реконекті ID завжди новий, тому не шукаємо старого)
        initial_data = {
            "alerts": [],
            "weather": [],
            "explosions": [],
            "missiles": [],
            "missiles2": [],
            "drones": [],
            "drones2": [],
            "kabs": [],
            "kabs2": [],
            "energy": [],
            "radiation": [],
            "global_notifications": {},
            "bins": [],
            "test_bins": [],
            "firmware": "unknown",
            "chip_id": "unknown",
            "latency": -1,
            # "alerts_fusion": {},
            # "weather_fusion": {},
            # "notifications_fusion": {},
            "initial": True,  # for v5
            # "alerts_hash": 0,  # for v5
            "city": geo_ip_data["city"],
            "region": geo_ip_data["region"],
            "country": geo_ip_data["country"],
            "timezone": geo_ip_data["timezone"],
            "org": geo_ip_data["org"],
            "location": geo_ip_data["loc"],
            "secure_connection": secure_connection,
            "connect_time": datetime.datetime.now(tz=server_timezone).strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # Створюємо Redis-backed клієнта з TTL 120 секунд (2 хвилини)
        # Це забезпечує збереження даних на випадок несподіваного завершення сервера
        client = await create_redis_backed_client(client_key, shared_data.redis_client, initial_data, ttl=120)
        # Зберігаємо клієнта в shared_data.clients для доступу з фонових задач
        shared_data.clients[client_key] = client

        chip_id_event = asyncio.Event()
        firmware_event = asyncio.Event()

        match websocket.request.path:
            case "/data_v1":
                producer_task = asyncio.create_task(
                    alerts_data(
                        websocket,
                        client,
                        client_id,
                        client_ip,
                        shared_data,
                        AlertVersion.v1,
                        chip_id_event,
                        firmware_event,
                    ),
                    name=f"alerts_data_{client_id}",
                )

            case "/data_v2":
                producer_task = asyncio.create_task(
                    alerts_data(
                        websocket,
                        client,
                        client_id,
                        client_ip,
                        shared_data,
                        AlertVersion.v2,
                        chip_id_event,
                        firmware_event,
                    ),
                    name=f"alerts_data_{client_id}",
                )

            case "/data_v3":
                producer_task = asyncio.create_task(
                    alerts_data(
                        websocket,
                        client,
                        client_id,
                        client_ip,
                        shared_data,
                        AlertVersion.v3,
                        chip_id_event,
                        firmware_event,
                    ),
                    name=f"alerts_data_{client_id}",
                )

            case "/data_v4":
                producer_task = asyncio.create_task(
                    alerts_data(
                        websocket,
                        client,
                        client_id,
                        client_ip,
                        shared_data,
                        AlertVersion.v4,
                        chip_id_event,
                        firmware_event,
                    ),
                    name=f"alerts_data_{client_id}",
                )

            case "/data_fusion_v1":
                producer_task = asyncio.create_task(
                    alerts_data_fusion(
                        websocket,
                        client,
                        client_id,
                        client_ip,
                        shared_data,
                        AlertVersion.v1,
                        chip_id_event,
                        firmware_event,
                    ),
                    name=f"alerts_data_{client_id}",
                )

            case _:
                logger.warning(f"{client_ip}:{client_id}: unknown path connection")
                return
        consumer_task = asyncio.create_task(
            message_handler(
                websocket,
                client,
                client_id,
                client_ip,
                geo_ip_data["country"],
                geo_ip_data["region"],
                geo_ip_data["city"],
                chip_id_event,
                firmware_event,
            ),
            name=f"message_handler_{client_id}",
        )
        ping_pong_task = asyncio.create_task(
            ping_pong(websocket, client, client_id, client_ip),
            name=f"ping_pong_{client_id}",
        )
        done, pending = await asyncio.wait(
            [consumer_task, producer_task, ping_pong_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        chip_id = get_chip_id(client, client_id)
        for finished in done:
            if exception := finished.exception():
                logger.debug(f"{client_ip}:{chip_id} !!! task {finished.get_name()} finished, exception: {exception}")
            else:
                logger.debug(f"{client_ip}:{chip_id} !!! task {finished.get_name()} finished")
        if pending:
            for task in pending:
                logger.debug(f"{client_ip}:{chip_id} >>> cancel task {task.get_name()}")
                task.cancel()
            await asyncio.wait(pending)
    except ConnectionClosedError as e:
        chip_id = get_chip_id(client, client_id) if client else client_id
        logger.debug(f"{client_ip}:{chip_id}: ConnectionClosedError - {e}")
    except Exception as e:
        chip_id = get_chip_id(client, client_id) if client else client_id
        logger.error(f"{client_ip}:{chip_id}: Exception - {e}", exc_info=True)
    finally:
        client_key = f"{client_ip}:{client_id}"

        # Видаляємо клієнта з пам'яті та Redis
        if client_key in shared_data.clients:
            del shared_data.clients[client_key]

        if client and isinstance(client, RedisBackedClient):
            try:
                await client.delete_from_redis()
                logger.debug(f"Client {client_key} deleted from Redis")
            except Exception as e:
                logger.error(f"Failed to delete client {client_key} from Redis: {e}")

        chip_id = get_chip_id(client, client_id) if client else client_id
        logger.info(f"{client_ip}:{chip_id} !!! end")


async def print_clients(shared_data, redis_client):
    # Локальний лік замість SCAN по всій БД. Увага: рахує тільки цей процес —
    # якщо dev-інстанс ділить REDIS_DB з prod, старий SCAN рахував обидва.
    pool = redis_client.connection_pool
    while True:
        try:
            await asyncio.sleep(60)
            logger.info(
                f"Clients: {len(shared_data.clients)}, "
                f"redis pool: {len(pool._in_use_connections)} in use / {len(pool._available_connections)} idle"
            )
        except Exception as e:
            logger.error(f"Error in print_clients: {e}")


def make_alert_batch(diff_region_ids: list[int], new_state: dict[int, int]) -> bytes:
    """
    Формат пакета:
    - region_id: 2 байти (unsigned short)
    - flags16: 2 байти (unsigned short)

    body: послідовність пар (region_id, flags16) для кожного регіону
    diff_region_ids: список регіонів з змінами(наприклад, [0, 1, 2, ...])
    new_state: повний словник даних тривог, де ключ — region_id, а значення — flags16 (наприклад, {0: 3, 1: 1, ...})
    """
    body = bytearray()
    for rid in diff_region_ids:
        flags16 = new_state.get(rid, 0)
        body += struct.pack("<H H", int(rid), flags16)
    return body


def make_weather_batch(new_state: dict[int, int]) -> bytes:
    """
    Формат пакета погоди:
    - region_id: 2 байти (unsigned short)
    - temp: 1 байт (unsigned char), попередньо закодований у 0..255
    body: послідовність пар (region_id, temp)
    """
    body = bytearray()
    for rid, temp in new_state.items():
        body += struct.pack("<H B", int(rid), int(temp) & 0xFF)
    return body


def make_grid_batch(new_state: dict[int, int]) -> bytes:
    """
    Формат пакета енергомережі (TYPE_GRID_BATCH = 0xA4):
    - region_id: 2 байти (unsigned short)
    - state: 1 байт (unsigned char)
    body: послідовність пар (region_id, state)
    """
    body = bytearray()
    for rid, state in new_state.items():
        body += struct.pack("<H B", int(rid), int(state) & 0xFF)
    return body


def make_radiation_batch(new_state: dict[int, int]) -> bytes:
    """
    Формат пакета радіації (TYPE_RADIATION_BATCH = 0xA5):
    - region_id: 2 байти (unsigned short)
    - value: 2 байти (unsigned short), діапазон 0..2000 не влазить у 1 байт
    body: послідовність пар (region_id, value)
    """
    body = bytearray()
    for rid, value in new_state.items():
        body += struct.pack("<H H", int(rid), int(value) & 0xFFFF)
    return body


def make_firmware_batch(releases: list, header) -> bytes:
    """
    Формат пакета прошивок (TYPE_FIRMWARE_UPDATE_BATCH = 0xA6):
    [Header: 1 byte] [Records: N * 5 bytes]
    Record (5 bytes, fixed):
      [Major: 1 byte]       - uint8
      [Minor: 1 byte]       - uint8
      [Patch: 1 byte]       - uint8
      [Beta: 2 bytes]       - uint16 little-endian (0 якщо не beta)
    Кількість записів = (length - 1) / 5
    Версія з тегу: "5.0.1" -> (5,0,1,0) | "5.0.0-b127" -> (5,0,0,127)
    """

    def parse_tag(tag: str):
        is_beta = "-b" in tag
        parts = tag.split("-b")
        nums = parts[0].split(".")
        major = int(nums[0]) if len(nums) > 0 else 0
        minor = int(nums[1]) if len(nums) > 1 else 0
        patch = int(nums[2]) if len(nums) > 2 else 0
        beta = int(parts[1]) if is_beta and len(parts) > 1 else 0
        return major, minor, patch, beta

    header = struct.pack("<B", header)
    records = bytearray()
    seen = set()
    for release in releases:
        major, minor, patch, beta = parse_tag(release["tag"])
        key = (major, minor, patch, beta)
        if key in seen:
            continue
        seen.add(key)
        records += struct.pack("<BBBH", major, minor, patch, beta)
    return header + records


def hex_payload(payload_hex, redis_key: str, client_ip: str = "", chip_id: str = "") -> bytes | bool:
    prefix = f"{client_ip}:{chip_id} " if client_ip or chip_id else ""
    if not payload_hex:
        logger.debug(f"{prefix}!!! empty hex payload for {redis_key}, skip send")
        return False
    if not isinstance(payload_hex, str):
        logger.debug(f"{prefix}!!! invalid hex payload type {type(payload_hex).__name__} for {redis_key}, skip send")
        return False
    try:
        return bytes.fromhex(payload_hex)
    except (TypeError, ValueError):
        logger.debug(f"{prefix}!!! invalid hex payload value for {redis_key}, skip send")
        return False


async def process_request(connection: ServerConnection, request: Request):
    client_ip = await get_client_ip(connection)
    # health check
    if request.path == "/healthz":
        logger.info(f"{client_ip}: health check")
        return connection.respond(HTTPStatus.OK, "OK\n")
    # check for valid path
    if not request.path.startswith("/data_v") and not request.path.startswith("/data_fusion_v"):
        logger.error(f"{client_ip}: invalid path - {request.path}")
        return connection.respond(HTTPStatus.NOT_FOUND, "Not Found\n")


async def process_response(connection: ServerConnection, request: Request, response: Response):
    client_ip = await get_client_ip(connection)
    if connection.protocol.handshake_exc:
        logger.error(f"{client_ip}: invalid handshake - {connection.protocol.handshake_exc}")
        # clear exception, already handled
        connection.protocol.handshake_exc = None


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
        # Стеля пулу. Пул КИДАЄ ConnectionError, а не чекає — тому стеля мусить бути вища
        # за суму всіх одночасних споживачів: 1 (redis_fanout) + 32 (handshake)
        # + 50 (geo_ip) + 8 (client_sync) = 91. Запас на сплески при масовому реконекті.
        # Значення 50 було замалим: під час старту get_redis_data глушив ConnectionError
        # і клієнти отримували початковий стан із default_response замість Redis.
        max_connections=REDIS_MAX_CONNECTIONS,
    )

    # Ініціалізуємо Redis client в shared_data для використання в get_geo_ip_data
    shared_data.redis_client = redis_client
    shared_data.http_session = aiohttp.ClientSession()
    logger.info("✅ Redis client and HTTP session initialized in shared_data")

    try:
        async with serve(
            echo,
            "0.0.0.0",
            websocket_port,
            process_request=process_request,
            process_response=process_response,
            ping_interval=None,
            ping_timeout=None,
        ):
            await asyncio.gather(
                redis_fanout(shared_data),
                print_clients(shared_data, redis_client),
            )
    finally:
        await shared_data.http_session.close()
        await redis_client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
