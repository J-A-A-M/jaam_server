"""Чиста логіка обробки погоди: legacy v1 та fusion (openweathermap/openmeteo)."""

from .common import encode_temperature_to_mask


def build_v1_weather(cache, regions, legacy_led_count):
    data = [0] * legacy_led_count
    for _, state_data in regions.items():
        legacy_state_id = state_data["legacyId"]
        state_id = state_data["stateId"]
        for state in cache:
            if state_id == state["region"]["regionId"]:
                data[legacy_state_id - 1] = int(round(state["temp"], 0))
    return data


def build_fusion_weather(cache, region_id_getter, temp_getter):
    """fusion: {regionId: temp_mask}. Гетери абстрагують різницю схем ow/openmeteo."""
    data = {}
    for region in cache:
        data[region_id_getter(region)] = encode_temperature_to_mask(temp_getter(region))
    return data
