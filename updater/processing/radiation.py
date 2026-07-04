"""Чиста логіка обробки радіації: legacy v1 та fusion (спільна агрегація сенсорів)."""

import datetime

# Сенсори Чорнобильської зони (is_cez) фонять у рази вище за решту області й
# тягнуть середнє Київської області вгору, тому рахуються окремо і мапляться
# на Припʼять
CEZ_REGION_ID = 8888  # Припʼять

# Страховка на випадок пропущеного прапорця is_cez у SaveEcoBot:
# сенсор у цих містах вважається сенсором зони незалежно від is_cez
# (напр., сенсор 22415 у Чорнобилі має is_cez=false).
CEZ_CITY_NAMES = {"Чорнобиль", "Прип'ять"}


def _is_stale(sensor_data, max_age_days, now):
    """Показання застаріле, якщо updated_at відсутній/непарсабельний або старший за max_age_days."""
    try:
        updated_at = datetime.datetime.fromisoformat(sensor_data.get("updated_at"))
    except (TypeError, ValueError):
        return True
    if updated_at.tzinfo:
        updated_at = updated_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return now - updated_at > datetime.timedelta(days=max_age_days)


def aggregate_sensor_readings(data_cache, sensors_cache, max_age_days=None, now=None):
    """Групує показники активних сенсорів за назвою області: {state_name: [gamma, ...]}.

    Сенсори Чорнобильської зони (is_cez) в обласні списки не потрапляють —
    їх показники повертаються окремим другим списком.

    max_age_days: додатково до is_old відкидає показання, старші за N днів
    (updated_at від SaveEcoBot — локальний час без зони, можлива похибка в
    кілька годин проти UTC, на масштабі днів несуттєва). None — без фільтра.
    """
    if max_age_days is not None and now is None:
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    temp_data = {}
    cez_readings = []
    for sensor_data in data_cache:
        if sensor_data["is_old"]:
            continue
        if max_age_days is not None and _is_stale(sensor_data, max_age_days, now):
            continue
        sensor_info = sensors_cache.get(str(sensor_data["sensor_id"]), {})
        if sensor_info.get("is_cez") or sensor_info.get("city_name") in CEZ_CITY_NAMES:
            cez_readings.append(sensor_data["gamma_nsv_h"])
            continue
        state_name = sensor_info.get("region_name")
        if not state_name:
            continue
        if not temp_data.get(state_name):
            temp_data[state_name] = []
        temp_data[state_name].append(sensor_data["gamma_nsv_h"])
    return temp_data, cez_readings


def build_v1_radiation(data_cache, sensors_cache, regions, legacy_led_count, max_age_days=None):
    temp_data, _ = aggregate_sensor_readings(data_cache, sensors_cache, max_age_days)
    data = [0] * legacy_led_count
    for _, state_data in regions.items():
        state_name = state_data["name"]
        legacy_state_id = state_data["legacyId"]
        state_radiation_data = temp_data.get(state_name, [])
        if state_radiation_data:
            data[legacy_state_id - 1] = round(sum(state_radiation_data) / len(state_radiation_data))
    return data


def build_fusion_radiation(data_cache, sensors_cache, regions, max_age_days=None):
    temp_data, cez_readings = aggregate_sensor_readings(data_cache, sensors_cache, max_age_days)
    data = {}
    for _, state_data in regions.items():
        state_name = state_data["name"]
        region_id = state_data["regionId"]
        state_radiation_data = temp_data.get(state_name, [])
        if state_radiation_data:
            # Діапазон радіації 0..2000 → не влазить у 1 байт, зберігаємо як ціле
            # Максимум замість середнього: показуємо найгірший фон у регіоні
            data[region_id] = round(max(state_radiation_data))
    if cez_readings:
        data[CEZ_REGION_ID] = round(max(cez_readings))
    return data
