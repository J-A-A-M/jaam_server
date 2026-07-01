"""Чиста логіка обробки глобальних сповіщень мапи."""


def build_global_notifications(cache):
    notifications = cache.get("mapNotifications", {})
    return {
        "mig": 1 if notifications.get("hasMig") else 0,
        "ships": 1 if notifications.get("hasBoats") else 0,
        "tactical": 1 if notifications.get("hasTacticalAviation") else 0,
        "strategic": 1 if notifications.get("hasStrategicAviation") else 0,
        "ballistic_missiles": 1 if notifications.get("hasBallistics") else 0,
        "mig_missiles": 1 if notifications.get("migRockets") else 0,
        "ships_missiles": 1 if notifications.get("boatsRockets") else 0,
        "tactical_missiles": 1 if notifications.get("tacticalAviationRockets") else 0,
        "strategic_missiles": 1 if notifications.get("strategicAviationRockets") else 0,
    }
