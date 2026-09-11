"""Спільні чисті функції обробки даних (без I/O).

Усі функції параметризовані: `regions` та `now` інжектяться аргументами, а не
читаються з глобалів модуля. Це дозволяє викликачу (updater.updater) лишити
патчабельні символи у своєму namespace для існуючих тестів.
"""

import datetime

NO_DATA_TIMESTAMP = 1645674000


def parse_iso_utc(value):
    """ISO-8601 => tz-aware datetime у UTC. Naive (без офсету) трактується як UTC.

    Уникає TypeError при порівнянні naive/aware дат, коли зовнішній API дає
    неузгоджені формати createdAt/lastUpdate. Python 3.13 fromisoformat парсить
    суфікс Z нативно.
    """
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def convert_region_ids(regions, key_value, initial_key, result_key):
    for _, region_data in regions.items():
        if region_data[initial_key] == key_value and not region_data.get("skip"):
            return region_data["name"], region_data[result_key]
    return None, None


def get_legacy_state_id(regions, region_id):
    try:
        for _, region_data in regions.items():
            if region_data["regionId"] == int(region_id):
                return region_data["legacyId"]
        return None
    except (KeyError, ValueError, TypeError):
        return None


def encode_temperature_to_mask(temp_c) -> int:
    """
    Упаковує температуру у бітову маску (1 байт).
    Діапазон значень: від -127 до 127 включно.
    Схема кодування:
    - біти [0..6] (7 біт): модуль температури (0..127)
    - біт [7]: знак (1 — від'ємна, 0 — додатна або нуль)
    Приклад:
    +25 -> 0b0011001 (25)
    -12 -> 0b1_0001100 (128 + 12 = 140)
    """
    try:
        t = int(round(float(temp_c), 0))
    except Exception:
        return 0
    # Обмежуємо діапазон
    if t < -127:
        t = -127
    elif t > 127:
        t = 127
    sign = 1 if t < 0 else 0
    magnitude = -t if t < 0 else t  # 0..127
    return (sign << 7) | magnitude


def check_states(data, cache, now):
    """Оновлює стан тривог: гасить активну тривогу, що зникла (`now` інжектується)."""
    index = 0
    for old_alert_data in cache:
        new_alert_data = data[index]
        is_new_alert = bool(new_alert_data[0] in [1, 2])
        is_old_alert = bool(old_alert_data[0] in [1, 2])
        is_new_data_set = bool(new_alert_data[1] != NO_DATA_TIMESTAMP)
        is_old_data_set = bool(old_alert_data[1] != NO_DATA_TIMESTAMP)

        if not is_new_alert and is_old_alert and is_old_data_set:
            data[index] = [0, now]
        if not is_new_alert and not is_old_alert and not is_new_data_set and is_old_data_set:
            data[index] = [0, old_alert_data[1]]

        index += 1


def check_notifications(data, cache):
    """Не дає таймстемпам відкотитись назад: лишає більше зі старого/нового."""
    index = 0
    for old_data in cache:
        new_data = data[index]

        if new_data < old_data:
            data[index] = old_data

        index += 1


def calculate_reason_date(websocket, legacy_state_id, now):
    old_alert_data = websocket[legacy_state_id - 1]
    is_old_state_alert = bool(old_alert_data[0] == 1)
    is_old_district_alert = bool(old_alert_data[0] == 2)
    if is_old_district_alert or is_old_state_alert:
        return old_alert_data[1]
    else:
        return now
