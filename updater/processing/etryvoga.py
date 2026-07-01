"""Чиста логіка обробки etryvoga-сповіщень: legacy v1 та fusion v1/v2."""

import datetime
import struct

from .common import NO_DATA_TIMESTAMP

# fusion v1 (повний потік): тип сповіщення -> біт
ETRYVOGA_FUSION_BIT_MAP = {
    "DRONE": 1 << 5,
    "ROCKET": 1 << 6,
    "KAB": 1 << 7,
    "BALLISTIC": 1 << 8,
    "EXPLOSION": 1 << 9,
    "RECON_DRONE": 1 << 10,
}


def build_etryvoga_v1_data(cache, alerts_websocket, regions, legacy_led_count):
    """Legacy v1: {stateId: iso_time} + опційний стан тривог -> список таймстемпів.

    `alerts_websocket=None` означає, що alert_key не задано (тривоги не враховуються).
    """
    data = [NO_DATA_TIMESTAMP] * legacy_led_count

    for _, state_data in regions.items():
        state_id = state_data["regionId"]
        state_id_str = str(state_id)
        legacy_state_id = state_data["legacyId"]
        if alerts_websocket is not None:
            is_alert = True if alerts_websocket[legacy_state_id - 1][0] == 1 else False
        else:
            is_alert = False
        if state_id_str in cache and not is_alert:
            alert_start_time = cache[state_id_str]
            alert_start_time = int(datetime.datetime.fromisoformat(alert_start_time.replace("Z", "+00:00")).timestamp())
            if alert_start_time > data[legacy_state_id - 1]:
                data[legacy_state_id - 1] = alert_start_time

    return data


def build_fusion_v1_etryvoga(alerts_cache, last_processed_id):
    """fusion v1: повний потік сповіщень -> ({regionId: flags16}, first_processed_id)."""
    data = {}
    first_processed_id = None

    for alert in alerts_cache:
        alert_id = int(alert["id"])

        if first_processed_id is None:
            first_processed_id = alert_id
        if alert_id <= last_processed_id:
            continue

        region_id = alert["regionId"]
        if region_id not in data:
            data[region_id] = 0

        bit = ETRYVOGA_FUSION_BIT_MAP.get(alert["type"])
        if bit is not None:
            data[region_id] |= bit

        if data[region_id] == 0:
            del data[region_id]

    return data, first_processed_id


def build_notifications_payload(region_ids, type_notifications_batch, flags_for):
    """Пакує notifications-payload. `flags_for(region_id)` повертає flags16 для регіону."""
    header = struct.pack("<B", type_notifications_batch)
    notifications = bytearray()
    for region_id in region_ids:
        notifications += struct.pack("<H H", int(region_id), flags_for(region_id))
    return (header + notifications).hex()
