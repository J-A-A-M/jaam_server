"""Чиста логіка визначення рівня тривоги Києва з fusion-прапорців (без side-effects)."""

# Ті самі прапорці flags16, що будує build_fusion_alerts_state() в updater/processing/alerts.py.
BIT_AIR_ACTIVE = 1 << 0
BIT_AIR_YELLOW = 1 << 11
BIT_AIR_RED = 1 << 12


def resolve_level(flags16):
    """flags16 з fusion-хешу websocket:v1:fusion:alerts:data => "green"/"yellow"/"red".

    Fail-safe: тривога активна, але без явного біта рівня (не мало б траплятись,
    build_fusion_alerts_state завжди ставить 11 або 12 разом з 0) => "red",
    щоб не занижувати серйозність сповіщення.
    """
    if not flags16 & BIT_AIR_ACTIVE:
        return "green"
    if flags16 & BIT_AIR_RED:
        return "red"
    if flags16 & BIT_AIR_YELLOW:
        return "yellow"
    return "red"
