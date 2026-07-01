"""Чиста логіка обробки тривог (alerts): legacy v1/v2 та fusion."""

import datetime
import struct

from .common import (
    NO_DATA_TIMESTAMP,
    calculate_reason_date,
    convert_region_ids,
    get_legacy_state_id,
)


def build_v1_alerts(alerts_cache, regions, legacy_led_count):
    alerts = [0] * legacy_led_count
    for alert in alerts_cache:
        for active_alert in alert["activeAlerts"]:
            region_id = active_alert["regionId"]
            region_type = active_alert["regionType"]
            legacy_state_id = get_legacy_state_id(regions, region_id)
            if not legacy_state_id:
                continue
            alert_type = active_alert["type"]
            if alert_type in ["AIR"] and region_type in ["State", "District"]:
                alerts[legacy_state_id - 1] = 1
    return alerts


def build_v2_alerts(alerts_cache, websocket, regions, legacy_led_count):
    alerts = [[0, NO_DATA_TIMESTAMP]] * legacy_led_count
    for alert in alerts_cache:
        if alert["regionType"] not in ["State", "District"]:
            continue
        state_alert = any(item["regionType"] == "State" for item in alert["activeAlerts"])
        for active_alert in alert["activeAlerts"]:
            region_id = active_alert["regionId"]
            region_type = active_alert["regionType"]
            legacy_state_id = get_legacy_state_id(regions, region_id)
            if not legacy_state_id:
                continue
            alert_type = active_alert["type"]
            alert_start_time = active_alert["lastUpdate"]
            alert_start_time = int(datetime.datetime.fromisoformat(alert_start_time.replace("Z", "+00:00")).timestamp())
            old_alert_data = websocket[legacy_state_id - 1]
            is_old_state_alert = bool(old_alert_data[0] == 1)
            if alert_type in ["AIR"]:
                if region_type == "District" and not state_alert:
                    if is_old_state_alert:
                        alerts[legacy_state_id - 1] = [1, old_alert_data[1]]
                    else:
                        alerts[legacy_state_id - 1] = [1, alert_start_time]
                if region_type == "State":
                    if is_old_state_alert:
                        alerts[legacy_state_id - 1] = [1, old_alert_data[1]]
                    else:
                        alerts[legacy_state_id - 1] = [1, alert_start_time]
    return alerts


def build_alert_reasons(reasons, alerts_cache, websocket_data, default_value, alert_type, regions, now):
    alerts = default_value.copy()
    for reason in reasons:
        region_id = int(reason["regionId"])
        state_id = int(reason["parentRegionId"])
        _, legacy_state_id = convert_region_ids(regions, state_id, "regionId", "legacyId")
        if not legacy_state_id:
            continue

        if alert_type in reason["alertTypes"]:
            for alert in alerts_cache:
                if int(alert["regionId"]) == region_id:
                    for active_alert in alert["activeAlerts"]:
                        if active_alert["type"] == "AIR" and int(active_alert["regionId"]) == region_id:
                            alerts[legacy_state_id - 1] = [
                                1,
                                calculate_reason_date(websocket_data, legacy_state_id, now),
                            ]
    return alerts


def build_fusion_alerts_state(alerts_cache, reasons):
    """Будує {regionId: flags16} для fusion-протоколу з тривог + причин."""
    new_state = {}

    for alert in alerts_cache:
        for active_alert in alert["activeAlerts"]:
            region_id = active_alert["regionId"]
            if region_id not in new_state:
                new_state[region_id] = 0
            if active_alert["type"] == "AIR":
                new_state[region_id] |= 1 << 0
            if active_alert["type"] == "ARTILLERY":
                new_state[region_id] |= 1 << 1
            if active_alert["type"] == "URBAN_FIGHTS":
                new_state[region_id] |= 1 << 2
            if active_alert["type"] == "CHEMICAL":
                new_state[region_id] |= 1 << 3
            if active_alert["type"] == "NUCLEAR":
                new_state[region_id] |= 1 << 4

    for reason_alert in reasons:
        region_id = reason_alert["regionId"]
        if region_id not in new_state:
            new_state[region_id] = 0
        for alert_type in reason_alert["alertTypes"]:
            if alert_type == "Drones":
                new_state[region_id] |= 1 << 5
            if alert_type == "Missile":
                new_state[region_id] |= 1 << 6

    return new_state


def find_empty_regions(old_state, new_state):
    """Регіони, присутні у старому стані, але відсутні у новому."""
    return [region_id for region_id in old_state.keys() if region_id not in new_state]


def find_changed_regions(old_state, new_state):
    """Регіони, де flags16 змінився відносно старого стану."""
    return [region_id for region_id, flags16 in new_state.items() if old_state.get(region_id) != flags16]


def calc_body_alerts_hash(body_alerts) -> int:
    """Простий 16-бітний хеш для тіла alerts-пакета."""
    return sum(body_alerts) % 0x10000  # 65536


def build_alerts_payload(new_state, changed_region_ids, empty_region_ids, hash_previous_value, type_alerts_batch):
    """Пакує fusion alerts-payload. Повертає (payload_bytes, hash_current)."""
    alerts_header = struct.pack("<B", type_alerts_batch)
    alerts = bytearray()

    for region_id in changed_region_ids + empty_region_ids:
        flags16 = new_state.get(region_id, 0)
        alerts += struct.pack("<H H", int(region_id), flags16)

    hash_current_value = calc_body_alerts_hash(alerts)

    hash_actual = struct.pack("<H", hash_current_value)
    hash_previous = struct.pack("<H", hash_previous_value)

    payload = alerts_header + hash_actual + hash_previous + alerts
    return payload, hash_current_value
