"""Доступ до налаштувань магазину (Settings) + ефективна NP-конфігурація.

Пріоритет: значення з БД (Settings) > env-дефолт (config). Порожнє у БД => env.
"""

from __future__ import annotations

from dataclasses import dataclass

from app import config
from app.db import get_db
from app.models import Settings


def get_settings(db) -> Settings:
    """Повертає єдиний рядок налаштувань, створюючи його за потреби."""
    s = db.get(Settings, 1)
    if s is None:
        s = Settings(id=1, order_start_number=config.ORDER_START_NUMBER)
        db.add(s)
        db.flush()
    return s


def _eff(value, default):
    return value if value not in (None, "") else default


@dataclass
class NpConfig:
    api_key: str
    api_url: str
    sender_ref: str
    sender_contact_ref: str
    sender_phone: str
    sender_city_ref: str
    sender_address_ref: str
    payer_type: str
    payment_method: str
    cargo_type: str
    service_type: str
    default_weight: str
    seat_width: str
    seat_length: str
    seat_height: str


def load_np() -> NpConfig:
    """Ефективна NP-конфігурація (БД зі fallback на env)."""
    with get_db() as db:
        s = get_settings(db)
        return NpConfig(
            api_key=_eff(s.np_api_key, config.NP_API_KEY),
            api_url=config.NP_API_URL,
            sender_ref=_eff(s.np_sender_ref, config.NP_SENDER_REF),
            sender_contact_ref=_eff(s.np_sender_contact_ref, config.NP_SENDER_CONTACT_REF),
            sender_phone=_eff(s.np_sender_phone, config.NP_SENDER_PHONE),
            sender_city_ref=_eff(s.np_sender_city_ref, config.NP_SENDER_CITY_REF),
            sender_address_ref=_eff(s.np_sender_warehouse_ref, config.NP_SENDER_ADDRESS_REF),
            payer_type=_eff(s.np_payer_type, config.NP_PAYER_TYPE),
            payment_method=config.NP_PAYMENT_METHOD,
            cargo_type=config.NP_CARGO_TYPE,
            service_type=config.NP_SERVICE_TYPE,
            default_weight=_eff(s.np_default_weight, config.NP_DEFAULT_WEIGHT),
            seat_width=_eff(s.np_seat_width, config.NP_SEAT_WIDTH),
            seat_length=_eff(s.np_seat_length, config.NP_SEAT_LENGTH),
            seat_height=_eff(s.np_seat_height, config.NP_SEAT_HEIGHT),
        )
