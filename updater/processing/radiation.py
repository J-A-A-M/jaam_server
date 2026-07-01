"""Чиста логіка обробки радіації: legacy v1 та fusion (спільна агрегація сенсорів)."""


def aggregate_sensor_readings(data_cache, sensors_cache):
    """Групує показники активних сенсорів за назвою області: {state_name: [gamma, ...]}."""
    temp_data = {}
    for sensor_data in data_cache:
        if sensor_data["is_old"]:
            continue
        state_name = sensors_cache.get(str(sensor_data["sensor_id"]), {}).get("region_name")
        if not state_name:
            continue
        if not temp_data.get(state_name):
            temp_data[state_name] = []
        temp_data[state_name].append(sensor_data["gamma_nsv_h"])
    return temp_data


def build_v1_radiation(data_cache, sensors_cache, regions, legacy_led_count):
    temp_data = aggregate_sensor_readings(data_cache, sensors_cache)
    data = [0] * legacy_led_count
    for _, state_data in regions.items():
        state_name = state_data["name"]
        legacy_state_id = state_data["legacyId"]
        state_radiation_data = temp_data.get(state_name, [])
        if state_radiation_data:
            data[legacy_state_id - 1] = round(sum(state_radiation_data) / len(state_radiation_data))
    return data


def build_fusion_radiation(data_cache, sensors_cache, regions):
    temp_data = aggregate_sensor_readings(data_cache, sensors_cache)
    data = {}
    for _, state_data in regions.items():
        state_name = state_data["name"]
        region_id = state_data["regionId"]
        state_radiation_data = temp_data.get(state_name, [])
        if state_radiation_data:
            # Діапазон радіації 0..2000 → не влазить у 1 байт, зберігаємо як ціле
            # Медіана стійкіша до викидів окремих сенсорів, ніж середнє
            # data[region_id] = round(statistics.median(state_radiation_data))
            data[region_id] = round(sum(state_radiation_data) / len(state_radiation_data))
    return data
