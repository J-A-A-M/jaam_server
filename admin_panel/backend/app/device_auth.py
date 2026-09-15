"""Похідний device-secret для jaam_touch chip_id whitelist.

Секрет НІКОЛИ не зберігається (ні тут, ні в Redis) — лише обчислюється з
DEVICE_AUTH_MASTER_SECRET + chip_id + secret_version, за тим самим алгоритмом,
що й `derive_device_secret` в корені jaam_server (utils.py), яку використовують
websocket_server/update_server для перевірки. Формула ідентична в обох місцях —
змінюй синхронно.
"""

import hashlib
import hmac

from .config import DEVICE_AUTH_MASTER_SECRET

_MASTER_SECRET = DEVICE_AUTH_MASTER_SECRET.encode()


def derive_device_secret(chip_id: str, secret_version: int) -> bytes:
    return hmac.new(_MASTER_SECRET, f"{chip_id.upper()}:{secret_version}".encode(), hashlib.sha256).digest()
