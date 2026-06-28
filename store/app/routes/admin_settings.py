"""Адмін-сторінка налаштувань Нова Пошта та нумерації замовлень."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app import nova_poshta
from app.core import admin_required, flash
from app.db import get_db
from app.np_settings import get_settings
from app.templating import render

_STR_FIELDS = [
    "np_api_key",
    "np_sender_ref",
    "np_sender_contact_ref",
    "np_sender_phone",
    "np_sender_city_ref",
    "np_sender_city_name",
    "np_sender_warehouse_ref",
    "np_sender_warehouse_name",
    "np_sender_warehouse_type",
    "np_default_weight",
    "np_seat_width",
    "np_seat_length",
    "np_seat_height",
    "np_payer_type",
]


@admin_required
async def np_config(request: Request):
    with get_db() as db:
        s = get_settings(db)
        return render(request, "admin/np_config.html", {"db": db, "s": s})


@admin_required
async def np_config_save(request: Request):
    form = await request.form()
    with get_db() as db:
        s = get_settings(db)
        for field in _STR_FIELDS:
            setattr(s, field, (form.get(field) or "").strip())
        try:
            s.order_start_number = max(1, int(form.get("order_start_number") or 1))
        except ValueError:
            s.order_start_number = 1
        flash(request, "Налаштування збережено.", "success")
    return RedirectResponse("/admin/np-config", status_code=303)


@admin_required
async def np_detect_sender(request: Request):
    """Авто-визначення відправника (ref/contact/phone) за ключем API."""
    try:
        info = await nova_poshta.detect_sender()
    except nova_poshta.NovaPoshtaError as e:
        flash(request, f"Не вдалося визначити відправника: {e}", "danger")
        return RedirectResponse("/admin/np-config", status_code=303)
    with get_db() as db:
        s = get_settings(db)
        s.np_sender_ref = info["ref"]
        s.np_sender_contact_ref = info["contact_ref"]
        if info.get("phone"):
            s.np_sender_phone = info["phone"]
        flash(request, "Відправника визначено та збережено.", "success")
    return RedirectResponse("/admin/np-config", status_code=303)


routes = [
    Route("/admin/np-config", np_config, methods=["GET"]),
    Route("/admin/np-config/save", np_config_save, methods=["POST"]),
    Route("/admin/np-config/detect-sender", np_detect_sender, methods=["POST"]),
]
