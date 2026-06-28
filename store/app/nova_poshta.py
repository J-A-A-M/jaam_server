"""Клієнт Nova Poshta API v2.0.

Документація: https://developers.novaposhta.ua/documentation
Усі виклики — POST JSON на NP_API_URL з {apiKey, modelName, calledMethod, methodProperties}.
"""

from __future__ import annotations

import logging
import re

import httpx

from app.np_settings import NpConfig, load_np

log = logging.getLogger("store.nova_poshta")

# CategoryOfWarehouse у відповіді API.
POSTOMAT_CATEGORY = "Postomat"
BRANCH_CATEGORY = "Branch"
# TypeOfWarehouseRef для фільтра саме поштоматів (відділень багато типів).
POSTOMAT_TYPE_REF = "f9316480-5f2d-425d-bc2c-ac7cd29decf0"


class NovaPoshtaError(Exception):
    pass


def enabled() -> bool:
    return bool(load_np().api_key)


_DESC_ALLOWED = re.compile(r"[^0-9A-Za-zА-Яа-яЇїІіЄєҐґ \.\,\-\/\(\)№'\"\+]")


def sanitize_description(text: str, limit: int = 250) -> str:
    """Прибирає символи, які відхиляє валідація Опису Нова Пошта (×, :, ; тощо)."""
    text = (text or "").replace("×", "x").replace(":", " -").replace(";", ",")
    text = _DESC_ALLOWED.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit] or "Замовлення"


def normalize_phone(phone: str) -> str:
    """Приводить телефон до формату 380XXXXXXXXX."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("380"):
        return digits
    if digits.startswith("0"):
        return "38" + digits
    if len(digits) == 9:
        return "380" + digits
    return digits


async def _call(model: str, method: str, props: dict, cfg: NpConfig | None = None) -> list:
    """Виклик API. Повертає список data або кидає NovaPoshtaError."""
    cfg = cfg or load_np()
    if not cfg.api_key:
        raise NovaPoshtaError("Ключ API Нова Пошта не налаштовано")
    payload = {
        "apiKey": cfg.api_key,
        "modelName": model,
        "calledMethod": method,
        "methodProperties": props,
    }
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(cfg.api_url, json=payload)
        data = resp.json()
    if not data.get("success"):
        errs = "; ".join(data.get("errors") or []) or "Невідома помилка Nova Poshta"
        raise NovaPoshtaError(errs)
    return data.get("data", [])


# --- Пошук міст / населених пунктів -----------------------------------------
async def search_cities(query: str, limit: int = 20) -> list[dict]:
    """Пошук населених пунктів. Повертає [{ref, name}] (ref = CityRef для відділень)."""
    if not query or len(query) < 2:
        return []
    data = await _call("Address", "searchSettlements", {"CityName": query, "Limit": str(limit)})
    addresses = data[0].get("Addresses", []) if data else []
    result = []
    for a in addresses:
        city_ref = a.get("DeliveryCity")
        if not city_ref:
            continue
        result.append({"ref": city_ref, "name": a.get("Present", "")})
    return result


# --- Відділення та поштомати -------------------------------------------------
async def get_warehouses(city_ref: str, query: str = "", category: str = "", limit: int = 50) -> dict:
    """Повертає {'branches': [...], 'postomats': [...]} для міста.

    category="postomat" — фільтрує лише поштомати (їх не видно в перших
    результатах серед відділень). Кожен елемент: {ref, number, name, type}.
    """
    if not city_ref:
        return {"branches": [], "postomats": []}
    props = {"CityRef": city_ref, "Limit": str(limit)}
    if query:
        props["FindByString"] = query
    if category == "postomat":
        props["TypeOfWarehouseRef"] = POSTOMAT_TYPE_REF
    data = await _call("AddressGeneral", "getWarehouses", props)
    branches, postomats = [], []
    for w in data:
        category = w.get("CategoryOfWarehouse", "")
        item = {
            "ref": w.get("Ref"),
            "number": w.get("Number"),
            "name": w.get("Description", ""),
            "type": category,
        }
        if category == POSTOMAT_CATEGORY:
            postomats.append(item)
        else:
            branches.append(item)
    return {"branches": branches, "postomats": postomats}


# --- Створення експрес-накладної (ЕН) ---------------------------------------
def _split_name(full_name: str) -> tuple[str, str, str]:
    """ПІБ -> (Прізвище, Імʼя, По батькові). Перше слово = прізвище."""
    parts = (full_name or "").split()
    last = parts[0] if parts else "Отримувач"
    first = parts[1] if len(parts) > 1 else "—"
    middle = " ".join(parts[2:]) if len(parts) > 2 else ""
    return last, first, middle


async def _create_recipient(full_name: str, phone: str, city_ref: str, cfg: NpConfig) -> tuple[str, str]:
    """Створює приватного отримувача. Повертає (RecipientRef, ContactRef)."""
    last, first, middle = _split_name(full_name)
    data = await _call(
        "Counterparty",
        "save",
        {
            "FirstName": first,
            "MiddleName": middle,
            "LastName": last,
            "Phone": normalize_phone(phone),
            "Email": "",
            "CounterpartyType": "PrivatePerson",
            "CounterpartyProperty": "Recipient",
            "CityRef": city_ref,
        },
        cfg,
    )
    rec = data[0]
    contact = rec.get("ContactPerson", {}).get("data", [{}])
    return rec.get("Ref"), (contact[0].get("Ref") if contact else "")


async def create_waybill(
    *,
    full_name: str,
    phone: str,
    city_ref: str,
    warehouse_ref: str,
    cost,
    description: str,
    weight: str = "",
    width: str = "",
    length: str = "",
    height: str = "",
    internal_number: str = "",
    seats: int = 1,
) -> dict:
    """Створює ЕН на відділення/поштомат. Повертає {number, ref}.

    Конфіг відправника/оплати/габаритів — з налаштувань (БД→env).
    internal_number => InfoRegClientBarcode (внутрішній номер у бізнес-кабінеті).
    """
    cfg = load_np()
    if not (cfg.sender_ref and cfg.sender_city_ref and cfg.sender_address_ref):
        raise NovaPoshtaError("Не налаштовано відправника (вкажіть у налаштуваннях Нова Пошта).")
    if not (city_ref and warehouse_ref):
        raise NovaPoshtaError("Замовлення не містить даних Нова Пошта (місто/відділення).")

    from datetime import datetime

    recipient_ref, recipient_contact = await _create_recipient(full_name, phone, city_ref, cfg)

    seat_weight = str(weight or cfg.default_weight)
    # OptionsSeat обовʼязковий для поштоматів (габарити місця). Передаємо завжди.
    options_seat = [
        {
            "volumetricWidth": str(width or cfg.seat_width),
            "volumetricLength": str(length or cfg.seat_length),
            "volumetricHeight": str(height or cfg.seat_height),
            "weight": seat_weight,
        }
    ]

    props = {
        "PayerType": cfg.payer_type,
        "PaymentMethod": cfg.payment_method,
        "DateTime": datetime.now().strftime("%d.%m.%Y"),
        "CargoType": cfg.cargo_type,
        "Weight": seat_weight,
        "ServiceType": cfg.service_type,
        "SeatsAmount": str(seats),
        "OptionsSeat": options_seat,
        "Description": sanitize_description(description),
        "Cost": str(int(round(float(cost)))),
        "CitySender": cfg.sender_city_ref,
        "Sender": cfg.sender_ref,
        "SenderAddress": cfg.sender_address_ref,
        "ContactSender": cfg.sender_contact_ref,
        "SendersPhone": normalize_phone(cfg.sender_phone),
        "CityRecipient": city_ref,
        "Recipient": recipient_ref,
        "RecipientAddress": warehouse_ref,
        "ContactRecipient": recipient_contact,
        "RecipientsPhone": normalize_phone(phone),
    }
    if internal_number:
        # InfoRegClientBarcodes (множина!) => "Внутрішній номер відправлення" в кабінеті.
        props["InfoRegClientBarcodes"] = str(internal_number)
    data = await _call("InternetDocument", "save", props, cfg)
    doc = data[0]
    return {"number": doc.get("IntDocNumber", ""), "ref": doc.get("Ref", "")}


# --- Авто-визначення відправника за ключем ----------------------------------
async def detect_sender() -> dict:
    """Повертає {ref, contact_ref, phone} відправника з акаунта ключа."""
    data = await _call("Counterparty", "getCounterparties", {"CounterpartyProperty": "Sender", "Page": "1"})
    if not data:
        raise NovaPoshtaError("Відправника не знайдено в акаунті ключа.")
    sender_ref = data[0].get("Ref")
    contacts = await _call("Counterparty", "getCounterpartyContactPersons", {"Ref": sender_ref, "Page": "1"})
    contact_ref = contacts[0].get("Ref") if contacts else ""
    phone = contacts[0].get("Phones", "") if contacts else ""
    return {"ref": sender_ref, "contact_ref": contact_ref, "phone": phone}
