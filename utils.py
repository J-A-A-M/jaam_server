import json
import datetime
import random
import asyncio
import hmac
import hashlib
import os
import time

TYPE_ALERTS_BATCH = 0xA1
TYPE_NOTIFICATIONS_BATCH = 0xA2
TYPE_WEATHER_BATCH = 0xA3
TYPE_GRID_BATCH = 0xA4
TYPE_RADIATION_BATCH = 0xA5
TYPE_FIRMWARE_UPDATE_BETA_BATCH = 0xA6
TYPE_FIRMWARE_UPDATE_PROD_BATCH = 0xA7
# jaam_touch має власні opcodes — не перевикористовує 0xA6/0xA7 jaam_fusion,
# щоб touch-прошивка не могла отримувати/парсити fusion-специфічні дані і навпаки.
TYPE_FIRMWARE_UPDATE_TOUCH_BETA_BATCH = 0xA8
TYPE_FIRMWARE_UPDATE_TOUCH_PROD_BATCH = 0xA9


# --- Device auth (jaam_touch chip_id whitelist) -----------------------------
# Секрет пристрою — похідний, не зберігається на сервері: derive_device_secret
# з тим самим DEVICE_AUTH_MASTER_SECRET обчислюється і в admin_panel (щоб один раз
# видати технiку), і тут (щоб перевірити HMAC від прошивки). У Redis/Postgres
# зберігається лише secret_version+whitelisted, жодного секретного матеріалу.
DEVICE_AUTH_MASTER_SECRET = (os.environ.get("DEVICE_AUTH_MASTER_SECRET") or "change-me-in-production").encode()
DEVICE_AUTH_TS_WINDOW_S = 120


def derive_device_secret(chip_id: str, secret_version: int) -> bytes:
    return hmac.new(DEVICE_AUTH_MASTER_SECRET, f"{chip_id.upper()}:{secret_version}".encode(), hashlib.sha256).digest()


def device_auth_key(chip_id: str) -> str:
    return f"device_auth:{chip_id.upper()}"


def device_claim_key(chip_id: str) -> str:
    return f"device_claim:{chip_id.upper()}"


def require_device_auth_master_secret_configured(consequence: str) -> None:
    """Fail-loud guard для entrypoint'ів: не даємо серверу стартувати з дефолтним секретом.

    `consequence` — повне речення про те, що стає тривіально підробним (узгодження роду/числа
    різне для websocket_server і update_server, тому текст лишаємо параметризованим цілком,
    а не третьою копією однакового if/raise).
    """
    if DEVICE_AUTH_MASTER_SECRET == b"change-me-in-production":
        raise RuntimeError(
            "DEVICE_AUTH_MASTER_SECRET не змінено! Виставте змінну оточення DEVICE_AUTH_MASTER_SECRET "
            f"перед запуском — інакше {consequence}."
        )


async def verify_device_auth(redis_client, chip_id, ts_str, mac_hex, domain: str) -> tuple[bool, str]:
    """Перевіряє HMAC-триплет (chip_id, ts, mac) пристрою jaam_touch проти whitelist у Redis.

    `domain` розділяє контексти підпису (напр. "WS" чи "OTA:<filename>"), щоб захоплений
    токен для одного контексту був непридатний для іншого. Повертає (ok, reason).
    """
    if not chip_id or not ts_str or not mac_hex:
        return False, "missing_fields"
    try:
        ts = int(ts_str)
    except (TypeError, ValueError):
        return False, "bad_ts"
    if abs(time.time() - ts) > DEVICE_AUTH_TS_WINDOW_S:
        return False, "ts_out_of_window"

    chip_id_upper = chip_id.upper()
    auth = await redis_client.hgetall(device_auth_key(chip_id_upper))
    # "unknown_device" (жодного запису - admin_panel ще не бачив цей chip_id) відрізняємо від
    # "not_whitelisted" (запис є, але адмін явно зняв whitelisted) лише для чіткості логів -
    # обидва однаково ведуть до відмови нижче за викликом.
    if not auth:
        return False, "unknown_device"
    if auth.get("whitelisted") != "1":
        return False, "not_whitelisted"

    try:
        secret_version = int(auth.get("version", 0))
    except (TypeError, ValueError):
        secret_version = 0

    secret = derive_device_secret(chip_id_upper, secret_version)
    expected = hmac.new(secret, f"{domain}:{chip_id_upper}:{ts}".encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac_hex.lower()):
        return False, "bad_mac"

    # Replay-захист: один (domain, chip_id, ts) валідний лише один раз. Без цього captured
    # HMAC-триплет можна відтворити скільки завгодно разів у межах DEVICE_AUTH_TS_WINDOW_S.
    nonce_key = f"device_auth_nonce:{domain}:{chip_id_upper}:{ts}"
    is_new = await redis_client.set(nonce_key, "1", nx=True, ex=DEVICE_AUTH_TS_WINDOW_S * 2)
    if not is_new:
        return False, "replayed"
    return True, "ok"


# Фільтр для бета-версій touch (одна апаратна версія — без c3/s3/lite винятків)
def touch_beta_filter(name):
    return "JAAM_TOUCH" in name and "-b" in name


def touch_release_filter(name):
    return "JAAM_TOUCH" in name and "-b" not in name


def truncate_name(name, max_length=30):
    if len(name) <= max_length:
        return name
    return name[: max_length - 3] + "..."


def get_current_datetime():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_time(time):
    try:
        # Спроба обробити формат без мікросекунд
        dt = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%SZ")
        formatted_timestamp = time  # Вже у потрібному форматі
    except ValueError:
        dt = datetime.datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%fZ")
        formatted_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return formatted_timestamp


def calculate_time_difference(timestamp1, timestamp2):
    format_str = "%Y-%m-%dT%H:%M:%SZ"

    time1 = datetime.datetime.strptime(timestamp1, format_str)
    time2 = datetime.datetime.strptime(timestamp2, format_str)

    time_difference = (time2 - time1).total_seconds()
    return int(abs(time_difference))


def get_random_proxy(proxies):
    if not proxies or proxies == "":
        return None
    return random.choice(proxies.split("::")).strip()


# Фільтр для бета-версій (лише з -b)
def beta_filter(name):
    return (
        "JAAM" in name
        and "-b" in name
        and "c3" not in name.lower()
        and "s3" not in name.lower()
        and "lite" not in name.lower()
    )


def release_filter(name):
    return (
        "JAAM" in name
        and "-b" not in name
        and "c3" not in name.lower()
        and "s3" not in name.lower()
        and "lite" not in name.lower()
    )


def get_file_names(logger, releases, filter_func=None, strip_pattern=None):
    if not releases:
        logger.warning("No releases data found in Redis")
        return []

    if filter_func:
        filtered_files = [
            {"name": f["name"], "tag": f["tag"], "url": f["url"]} for f in releases if filter_func(f["name"])
        ]
    else:
        filtered_files = [{"name": f["name"], "tag": f["tag"], "url": f["url"]} for f in releases]

    # Прибираємо маску де завгодно у назві файлу
    if strip_pattern:
        filtered_files = [
            {"name": f["name"].replace(strip_pattern, ""), "tag": f["tag"], "url": f["url"]} for f in filtered_files
        ]

    return filtered_files


async def service_is_fine(logger, redis_client, key):
    """
    Зберегти час останнього успішного виклику в Redis
    """
    await set_redis_data(logger, redis_client, key, get_current_datetime())


async def get_redis_data(logger, redis_client, key, default_response=None):
    """
    Отримати дані з Redis з підтримкою різних типів даних
    З коректним декодуванням UTF-8 для кирилиці

    Args:
        redis_client: Redis клієнт (з decode_responses=True)
        key: ключ для отримання даних
        default_response: значення за замовчуванням якщо дані не знайдено

    Returns:
        Дані з Redis або default_response
    """
    if default_response is None:
        default_response = {}

    try:
        # Перевіряємо тип даних в Redis
        data_type = await redis_client.type(key)

        if data_type == "none":
            return default_response
        elif data_type == "string":
            data = await redis_client.get(key)
            if data:
                try:
                    # Спробуємо розпарсити JSON (кирилиця вже декодована)
                    return json.loads(data)
                except json.JSONDecodeError:
                    # Якщо не JSON, повертаємо як рядок
                    return data
        elif data_type == "list":
            # Отримуємо всі елементи списку (вже в UTF-8)
            data = await redis_client.lrange(key, 0, -1)
            return [json.loads(item) if item else None for item in data]
        elif data_type == "hash":
            # Отримуємо всі поля хешу (вже в UTF-8)
            data = await redis_client.hgetall(key)
            return {k: json.loads(v) if v else None for k, v in data.items()}
        elif data_type == "set":
            # Отримуємо всі елементи множини (вже в UTF-8)
            data = await redis_client.smembers(key)
            return {json.loads(item) if item else None for item in data}
        elif data_type == "zset":
            # Отримуємо всі елементи відсортованої множини (вже в UTF-8)
            data = await redis_client.zrange(key, 0, -1, withscores=True)
            return [(json.loads(item), score) for item, score in data]

        return default_response
    except Exception as e:
        logger.error(f"Error getting data from Redis for key {key}: {e}")
        return default_response


async def get_redis_data_by_pattern(logger, redis_client, pattern):
    """
    Отримує всі дані з Redis по заданій масці

    Args:
        logger: Logger для логування
        redis_client: Redis клієнт
        pattern: Шаблон для пошуку ключів (наприклад, "websocket:clients:*")

    Returns:
        dict: Словник з ключами та їх значеннями
    """
    try:
        result = {}

        # Використовуємо SCAN для безпечного перегляду всіх ключів
        cursor = 0
        while True:
            cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)

            for key in keys:
                try:
                    # Отримуємо значення для кожного ключа
                    value = await redis_client.get(key)
                    if value:
                        # Якщо це JSON, розпарсимо його
                        try:
                            result[key] = json.loads(value)
                        except json.JSONDecodeError:
                            result[key] = value
                except Exception as e:
                    logger.error(f"Error getting key {key}: {e}")

            if cursor == 0:
                break

        return result
    except Exception as e:
        logger.error(f"Error scanning Redis with pattern {pattern}: {e}")
        return {}


async def set_redis_data(logger, redis_client, key, value, expiry=None):
    """
    Зберегти дані в Redis з автоматичним визначенням типу
    З коректним кодуванням UTF-8 для кирилиці

    Args:
        redis_client: Redis клієнт (з decode_responses=True)
        key: ключ для збереження
        value: значення (dict, list, set, str, int, float, bool)
        expiry: час життя в секундах (опціонально)

    Типи збереження:
        - dict -> Hash (якщо всі значення прості) або String (JSON)
        - list -> List або String (JSON)
        - set -> Set або String (JSON)
        - str/int/float/bool -> String
    """
    try:
        # Словник (dict) -> Hash або JSON String
        if isinstance(value, dict):
            # Перевіряємо чи всі значення можна зберегти як hash
            can_use_hash = all(isinstance(v, (str, int, float, bool, type(None))) for v in value.values())

            if can_use_hash and len(value) > 0:
                # Використовуємо Hash для простих словників
                pipeline = redis_client.pipeline()
                # Видаляємо старий ключ якщо існує
                pipeline.delete(key)
                # Додаємо всі поля (ensure_ascii=False для кирилиці)
                for k, v in value.items():
                    pipeline.hset(key, k, json.dumps(v, ensure_ascii=False))
                if expiry:
                    pipeline.expire(key, expiry)
                await pipeline.execute()
                logger.debug(f"Data stored in Redis as Hash with key: {key}")
            else:
                # Для складних структур використовуємо JSON (ensure_ascii=False для кирилиці)
                await redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=expiry)
                logger.debug(f"Data stored in Redis as JSON String with key: {key}")

        # Список (list) -> List
        elif isinstance(value, list):
            pipeline = redis_client.pipeline()
            pipeline.delete(key)
            if len(value) > 0:
                # Додаємо елементи списку (ensure_ascii=False для кирилиці)
                for item in value:
                    pipeline.rpush(key, json.dumps(item, ensure_ascii=False))
            else:
                # Для пустого списку створюємо порожній список
                pipeline.lpush(key, "")
                pipeline.lpop(key)
            if expiry:
                pipeline.expire(key, expiry)
            await pipeline.execute()
            logger.debug(f"Data stored in Redis as List with key: {key} ({len(value)} items)")

        # Множина (set) -> Set
        elif isinstance(value, set):
            pipeline = redis_client.pipeline()
            pipeline.delete(key)
            if len(value) > 0:
                # Додаємо елементи множини (ensure_ascii=False для кирилиці)
                for item in value:
                    pipeline.sadd(key, json.dumps(item, ensure_ascii=False))
            if expiry:
                pipeline.expire(key, expiry)
            await pipeline.execute()
            logger.debug(f"Data stored in Redis as Set with key: {key} ({len(value)} items)")

        # Прості типи -> String
        elif isinstance(value, (str, int, float, bool, type(None))):
            await redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=expiry)
            logger.debug(f"Data stored in Redis as String with key: {key}")

        # Інші типи -> JSON String
        else:
            await redis_client.set(key, json.dumps(value, ensure_ascii=False), ex=expiry)
            logger.debug(f"Data stored in Redis as JSON String with key: {key}")

    except Exception as e:
        logger.error(f"Error storing data in Redis for key {key}: {e}")


class Debouncer:
    """Debounce-механізм для asyncio: виконує корутину лише після паузи без нових викликів."""

    def __init__(self, delay: float):
        self.delay = delay
        self._delay_task: asyncio.Task | None = None
        self._run_task: asyncio.Task | None = None

    async def call(self, coro_func):
        """Скасовує попередній pending-виклик і планує новий через self.delay секунд."""
        if self._delay_task and not self._delay_task.done():
            self._delay_task.cancel()

        async def _run_after_delay():
            try:
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                return
            if self._run_task and not self._run_task.done():
                await self._run_task
            self._run_task = asyncio.create_task(coro_func())
            await self._run_task

        self._delay_task = asyncio.create_task(_run_after_delay())

    async def wait(self):
        """Чекає завершення поточного pending-виклику (для run_once)."""
        if self._delay_task and not self._delay_task.done():
            await self._delay_task
        if self._run_task and not self._run_task.done():
            await self._run_task

    def cancel(self):
        """Скасовує pending-виклик без очікування."""
        if self._delay_task and not self._delay_task.done():
            self._delay_task.cancel()


class Throttler:
    """Throttle-механізм для asyncio: при щільному потоку гарантовано виконує таску з певним періодом."""

    def __init__(self, period: float):
        self.period = period
        self._task: asyncio.Task | None = None
        self._pending: bool = False
        self._last_run: float | None = None

    async def call(self, coro_func):
        """Якщо таска не запущена — запускає одразу (або після залишку period).
        Якщо вже виконується — ставить pending, щоб запустити ще раз після завершення.
        """
        if self._task and not self._task.done():
            self._pending = True
            return

        async def _run():
            while True:
                if self._last_run is not None:
                    wait = self.period - (asyncio.get_running_loop().time() - self._last_run)
                    if wait > 0:
                        try:
                            await asyncio.sleep(wait)
                        except asyncio.CancelledError:
                            return
                self._last_run = asyncio.get_running_loop().time()
                self._pending = False
                await coro_func()
                if not self._pending:
                    break

        self._task = asyncio.create_task(_run())

    async def wait(self):
        """Чекає завершення поточного виконання (для run_once)."""
        if self._task and not self._task.done():
            await self._task

    def cancel(self):
        """Скасовує поточний виклик без очікування."""
        if self._task and not self._task.done():
            self._task.cancel()


async def run_with_restart(logger, func, redis_client, func_name, restart_delay=5):
    while True:
        try:
            logger.info(f"▶️  Запуск {func_name}")
            await func(redis_client)
        except asyncio.CancelledError:
            logger.warning(f"⏹️  {func_name} скасовано")
            raise
        except Exception as e:
            logger.error(f"❌ {func_name} впав з помилкою: {str(e)}")
            logger.debug(f"❌ Повний стек помилки:", exc_info=True)
            logger.info(f"🔄 Перезапуск {func_name} через {restart_delay} секунд...")
            await asyncio.sleep(restart_delay)
