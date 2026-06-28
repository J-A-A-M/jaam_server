"""Конфігурація магазину. 100% через env-змінні (стиль проєкту)."""

import os
import json
import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent  # .../app
PROJECT_DIR = BASE_DIR.parent  # .../store
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_DIR / "data"))

# --- База даних -------------------------------------------------------------
# За замовчуванням SQLite. Щоб перейти на іншу SQL-базу — достатньо задати
# DATABASE_URL (напр. postgresql+psycopg://user:pass@host/db).
_default_db_path = Path(os.getenv("STORE_DB_PATH", PROJECT_DIR / "var" / "store.db"))
_default_db_path.parent.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db_path}")

# --- Завантаження фото товарів ----------------------------------------------
# Каталог для завантажених фото (на volume у проді: /data/uploads).
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", PROJECT_DIR / "var" / "uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MEDIA_URL = "/media"  # префікс роздачі завантажених фото
# Дозволені типи фото (розширення -> content-type whitelist).
ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_IMAGE_BYTES = int(os.getenv("MAX_IMAGE_BYTES", str(8 * 1024 * 1024)))  # 8 МБ

# --- Безпека / сесії --------------------------------------------------------
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-insecure-secret-change-me")
# Майстер-ключ адміна: будь-який юзер, що введе його — стає адміном.
# БЕЗ дефолтного значення: предиктабельний дефолт = backdoor/auth-bypass.
# Якщо не заданий — вхід в адміни за майстер-ключем вимкнено (порожній ключ
# ніколи не збігається); адмінів усе одно можна створити згенерованими ключами.
MASTER_KEY = os.getenv("MASTER_KEY", "")
if not MASTER_KEY:
    logging.warning(
        "MASTER_KEY не задано — вхід в адмінку за майстер-ключем вимкнено. "
        "Задайте довгий випадковий MASTER_KEY для продакшену."
    )

# --- Мережа -----------------------------------------------------------------
PORT = int(os.getenv("PORT", "8090"))
HOST = os.getenv("HOST", "0.0.0.0")
LOGGING = os.getenv("LOGGING", "INFO")


# --- Нова Пошта API ---------------------------------------------------------
# Ключ — СЕКРЕТ, лише через env (не комітимо в код).
NP_API_KEY = os.getenv("NP_API_KEY", "")
NP_API_URL = os.getenv("NP_API_URL", "https://api.novaposhta.ua/v2.0/json/")

# Параметри відправника (магазину) для експрес-накладної.
NP_SENDER_REF = os.getenv("NP_SENDER_REF", "")
NP_SENDER_CONTACT_REF = os.getenv("NP_SENDER_CONTACT_REF", "")
NP_SENDER_PHONE = os.getenv("NP_SENDER_PHONE", "")
NP_SENDER_CITY_REF = os.getenv("NP_SENDER_CITY_REF", "")
NP_SENDER_ADDRESS_REF = os.getenv("NP_SENDER_ADDRESS_REF", "")

# Параметри ЕН за замовчуванням.
NP_PAYER_TYPE = os.getenv("NP_PAYER_TYPE", "Recipient")
NP_PAYMENT_METHOD = os.getenv("NP_PAYMENT_METHOD", "Cash")
NP_CARGO_TYPE = os.getenv("NP_CARGO_TYPE", "Parcel")
NP_SERVICE_TYPE = os.getenv("NP_SERVICE_TYPE", "WarehouseWarehouse")
NP_DEFAULT_WEIGHT = os.getenv("NP_DEFAULT_WEIGHT", "0.5")
# Габарити місця (см) — обовʼязкові для поштоматів (OptionsSeat).
NP_SEAT_WIDTH = os.getenv("NP_SEAT_WIDTH", "20")
NP_SEAT_LENGTH = os.getenv("NP_SEAT_LENGTH", "20")
NP_SEAT_HEIGHT = os.getenv("NP_SEAT_HEIGHT", "20")

if not NP_API_KEY:
    logging.warning("NP_API_KEY не задано — інтеграція Нова Пошта вимкнена.")

# Початковий номер замовлень (можна змінити в адмінці).
ORDER_START_NUMBER = int(os.getenv("ORDER_START_NUMBER", "1"))
