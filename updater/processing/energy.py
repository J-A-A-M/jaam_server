"""Чиста логіка обробки енергомережі: legacy v1 та fusion."""

from .common import NO_DATA_TIMESTAMP


def build_v1_energy(cache, websocket, regions, now, legacy_led_count):
    """Legacy v1: {stateId: state} -> [[state, date], ...]. `now` інжектується."""
    data = [[0, NO_DATA_TIMESTAMP]] * legacy_led_count
    for _, state_data in regions.items():
        legacy_state_id = state_data["legacyId"]
        state_id = state_data["stateId"]
        for state in cache:
            if state_id == state["regionId"]:
                old_state = websocket[legacy_state_id - 1][0]
                old_date = websocket[legacy_state_id - 1][1]
                new_state = state["state"]["id"]
                new_date = now if old_state != new_state else old_date
                data[legacy_state_id - 1] = [new_state, new_date]
    return data


def build_fusion_energy(cache):
    """fusion: {regionId: state_id}."""
    data = {}
    for state in cache:
        data[state["regionId"]] = state["state"]["id"]
    return data
