"""Юніт-тести чистої функції resolve_level (respublika_alert_notifier).

Ті самі біти flags16, що й у fusion-протоколі (build_fusion_alerts_state):
  - біт 0  — AIR активний
  - біт 11 — підсумок Yellow
  - біт 12 — підсумок Red
"""

from respublika_alert_notifier.logic import resolve_level

BIT_AIR = 1 << 0
BIT_AIR_YELLOW = 1 << 11
BIT_AIR_RED = 1 << 12


def test_no_air_bit_is_green():
    assert resolve_level(0) == "green"
    assert resolve_level(BIT_AIR_YELLOW) == "green"  # без біта 0 — тривога неактивна
    assert resolve_level(BIT_AIR_RED) == "green"


def test_air_with_yellow_bit_is_yellow():
    assert resolve_level(BIT_AIR | BIT_AIR_YELLOW) == "yellow"


def test_air_with_red_bit_is_red():
    assert resolve_level(BIT_AIR | BIT_AIR_RED) == "red"


def test_air_red_wins_when_both_bits_set():
    assert resolve_level(BIT_AIR | BIT_AIR_YELLOW | BIT_AIR_RED) == "red"


def test_air_without_level_bits_fails_safe_to_red():
    assert resolve_level(BIT_AIR) == "red"


def test_air_with_unrelated_bits_still_resolves():
    other_bits = (1 << 1) | (1 << 5)  # ARTILLERY + Drones reason, не стосуються AIR
    assert resolve_level(BIT_AIR | BIT_AIR_YELLOW | other_bits) == "yellow"
