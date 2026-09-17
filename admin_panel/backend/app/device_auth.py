"""Похідний device-secret для jaam_touch chip_id whitelist.

Секрет НІКОЛИ не зберігається (ні тут, ні в Redis) — лише обчислюється з
DEVICE_AUTH_MASTER_SECRET + chip_id + secret_version, за тим самим алгоритмом,
що й `derive_device_secret` в корені jaam_server (utils.py), яку використовують
websocket_server/update_server для перевірки. Формула ідентична в обох місцях —
змінюй синхронно.
"""

import hashlib
import hmac

from . import config


def derive_device_secret(chip_id: str, secret_version: int) -> bytes:
    # Читаємо config.DEVICE_AUTH_MASTER_SECRET лячно (не кешуємо в module-level змінну при
    # імпорті) - websocket_server/update_server теж читають свою копію з os.environ при
    # старті процесу, тож усі три місця однаково "заморожені" на час життя процесу, а не
    # ще й розсинхронізовані одне з одним залежно від порядку імпорту в цьому модулі.
    return hmac.new(
        config.DEVICE_AUTH_MASTER_SECRET.encode(), f"{chip_id.upper()}:{secret_version}".encode(), hashlib.sha256
    ).digest()
