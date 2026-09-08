"""Юніт-тести чистої функції build_fusion_alerts_state (fusion-протокол, flags16).

Поведінка AIR + activeAlertLevels:
  - AIR завжди ставить легасі біт 0
  - підсумок Red  => додатково біт 12
  - підсумок Yellow => додатково біт 11
"""

from updater.processing.alerts import build_fusion_alerts_state

BIT_AIR = 1 << 0  # легасі, ставиться для будь-якого AIR
BIT_ARTILLERY = 1 << 1
BIT_DRONES = 1 << 5
BIT_MISSILE = 1 << 6
BIT_AIR_YELLOW = 1 << 11
BIT_AIR_RED = 1 << 12

AIR_RED = BIT_AIR | BIT_AIR_RED  # 4097
AIR_YELLOW = BIT_AIR | BIT_AIR_YELLOW  # 2049


def _lvl(alert_level, reason, created_at):
    return {"alertLevel": alert_level, "reason": reason, "createdAt": created_at}


def _air(region_id, levels=None):
    active = {"regionId": region_id, "regionType": "State", "type": "AIR"}
    if levels is not None:
        active["activeAlertLevels"] = levels
    return {"regionId": region_id, "activeAlerts": [active]}


def _assert_legacy_bit(flags):
    """Легасі біт 0 має бути виставлений скрізь, де є AIR (біт 11 або 12)."""
    if flags & (BIT_AIR_YELLOW | BIT_AIR_RED):
        assert flags & BIT_AIR, f"легасі біт 0 відсутній у flags={flags:#b}"


def test_air_without_levels_field_is_red():
    """Старий формат без activeAlertLevels => Red => біти 0 + 12."""
    result = build_fusion_alerts_state([_air("31")], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])


def test_air_empty_levels_is_red():
    result = build_fusion_alerts_state([_air("31", [])], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])


def test_air_all_yellow_sets_bit_11_plus_legacy():
    levels = [
        _lvl("Yellow", "Дронова загроза Печерський р-н", "2026-09-07T16:39:08.655797Z"),
        _lvl("Yellow", "Дронова загроза Оболонський р-н", "2026-09-07T16:39:09.398597Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_YELLOW}
    _assert_legacy_bit(result["31"])


def test_air_any_red_sets_bit_12_plus_legacy():
    levels = [
        _lvl("Yellow", "Дронова загроза Печерський р-н", "2026-09-07T16:39:08.655797Z"),
        _lvl("Red", "Ракетна загроза Печерський р-н", "2026-09-07T16:42:33.179057Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])


def test_same_reason_newer_yellow_wins():
    """Один reason: старий Red + новіший Yellow => Yellow => біти 0 + 11."""
    levels = [
        _lvl("Red", "Ракетна загроза Печерський р-н", "2026-09-07T16:00:00.0Z"),
        _lvl("Yellow", "Ракетна загроза Печерський р-н", "2026-09-07T16:42:33.179057Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_YELLOW}
    _assert_legacy_bit(result["31"])


def test_same_reason_newer_red_wins():
    levels = [
        _lvl("Yellow", "Ракетна загроза Печерський р-н", "2026-09-07T16:00:00.0Z"),
        _lvl("Red", "Ракетна загроза Печерський р-н", "2026-09-07T16:42:33.179057Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])


def test_two_reasons_latest_has_red():
    levels = [
        _lvl("Red", "reason A", "2026-09-07T16:00:00.0Z"),
        _lvl("Yellow", "reason A", "2026-09-07T16:30:00.0Z"),  # A -> Yellow
        _lvl("Yellow", "reason B", "2026-09-07T16:00:00.0Z"),
        _lvl("Red", "reason B", "2026-09-07T16:30:00.0Z"),  # B -> Red
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])


def test_two_reasons_all_latest_yellow():
    levels = [
        _lvl("Red", "reason A", "2026-09-07T16:00:00.0Z"),
        _lvl("Yellow", "reason A", "2026-09-07T16:30:00.0Z"),
        _lvl("Red", "reason B", "2026-09-07T16:00:00.0Z"),
        _lvl("Yellow", "reason B", "2026-09-07T16:30:00.0Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_YELLOW}
    _assert_legacy_bit(result["31"])


def test_non_air_ignores_levels():
    """ARTILLERY з activeAlertLevels => біт 1, рівень не впливає, біта 0 нема."""
    alert = {
        "regionId": "31",
        "activeAlerts": [
            {
                "regionId": "31",
                "type": "ARTILLERY",
                "activeAlertLevels": [_lvl("Yellow", "x", "2026-09-07T16:00:00.0Z")],
            }
        ],
    }
    assert build_fusion_alerts_state([alert], []) == {"31": BIT_ARTILLERY}


def test_reasons_param_drones_missile_unchanged():
    reasons = [{"regionId": "13", "alertTypes": ["Drones", "Missile"]}]
    assert build_fusion_alerts_state([], reasons) == {"13": BIT_DRONES | BIT_MISSILE}


def test_air_yellow_combined_with_reason_drones():
    levels = [_lvl("Yellow", "Дронова загроза", "2026-09-07T16:39:08.655797Z")]
    reasons = [{"regionId": "31", "alertTypes": ["Drones"]}]
    result = build_fusion_alerts_state([_air("31", levels)], reasons)
    assert result == {"31": AIR_YELLOW | BIT_DRONES}
    _assert_legacy_bit(result["31"])


def test_kyiv_real_payload_resolves_red():
    """Реальний приклад: Київ, Yellow дрони + Red ракети => Red => біти 0 + 12."""
    levels = [
        _lvl("Yellow", "Дронова загроза (жовтий рівень) Печерський район", "2026-09-07T16:39:08.655797Z"),
        _lvl("Yellow", "Дронова загроза (жовтий рівень) Оболонський район", "2026-09-07T16:39:09.398597Z"),
        _lvl("Red", "Ракетна загроза (червоний рівень) Печерський район", "2026-09-07T16:42:33.179057Z"),
        _lvl("Red", "Ракетна загроза (червоний рівень) Дніпровський район", "2026-09-07T16:42:34.438518Z"),
    ]
    result = build_fusion_alerts_state([_air("31", levels)], [])
    assert result == {"31": AIR_RED}
    _assert_legacy_bit(result["31"])
