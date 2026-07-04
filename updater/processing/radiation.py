"""Чиста логіка обробки радіації: legacy v1 та fusion (спільна агрегація сенсорів)."""

# Сенсори Чорнобильської зони (is_cez) фонять у рази вище за решту області й
# тягнуть середнє Київської області вгору, тому рахуються окремо і мапляться
# на Вишгородський район (зона відчуження лежить у його межах).
CEZ_REGION_ID = 74  # Вишгородський район

# Страховка на випадок пропущеного прапорця is_cez у SaveEcoBot:
# сенсор у цих містах вважається сенсором зони незалежно від is_cez
# (напр., сенсор 22415 у Чорнобилі має is_cez=false).
CEZ_CITY_NAMES = {"Чорнобиль", "Прип'ять"}


def aggregate_sensor_readings(data_cache, sensors_cache):
    """Групує показники активних сенсорів за назвою області: {state_name: [gamma, ...]}.

    Сенсори Чорнобильської зони (is_cez) в обласні списки не потрапляють —
    їх показники повертаються окремим другим списком.
    """
    temp_data = {}
    cez_readings = []
    for sensor_data in data_cache:
        if sensor_data["is_old"]:
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


def build_v1_radiation(data_cache, sensors_cache, regions, legacy_led_count):
    temp_data, _ = aggregate_sensor_readings(data_cache, sensors_cache)
    data = [0] * legacy_led_count
    for _, state_data in regions.items():
        state_name = state_data["name"]
        legacy_state_id = state_data["legacyId"]
        state_radiation_data = temp_data.get(state_name, [])
        if state_radiation_data:
            data[legacy_state_id - 1] = round(sum(state_radiation_data) / len(state_radiation_data))
    return data


def build_fusion_radiation(data_cache, sensors_cache, regions):
    temp_data, cez_readings = aggregate_sensor_readings(data_cache, sensors_cache)
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
