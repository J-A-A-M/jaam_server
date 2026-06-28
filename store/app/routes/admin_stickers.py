"""Адмін-маршрути: стікери на товар ("Розпродаж", "Хіт" тощо)."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app.core import admin_required, flash
from app.db import get_db
from app.models import Sticker
from app.templating import render


@admin_required
async def stickers_list(request: Request):
    with get_db() as db:
        stickers = db.query(Sticker).order_by(Sticker.name).all()
        return render(request, "admin/stickers.html", {"db": db, "stickers": stickers})


@admin_required
async def sticker_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    color = (form.get("color") or "#dc3545").strip()
    text_color = (form.get("text_color") or "#ffffff").strip()
    if not name:
        flash(request, "Назва стікера не може бути порожньою.", "danger")
        return RedirectResponse("/admin/stickers", status_code=303)
    with get_db() as db:
        db.add(Sticker(name=name, color=color, text_color=text_color))
    flash(request, f"Стікер «{name}» створено.", "success")
    return RedirectResponse("/admin/stickers", status_code=303)


@admin_required
async def sticker_edit(request: Request):
    sticker_id = request.path_params["id"]
    form = await request.form()
    name = (form.get("name") or "").strip()
    color = (form.get("color") or "#dc3545").strip()
    text_color = (form.get("text_color") or "#ffffff").strip()
    with get_db() as db:
        sticker = db.get(Sticker, sticker_id)
        if sticker is None:
            flash(request, "Стікер не знайдено.", "danger")
            return RedirectResponse("/admin/stickers", status_code=303)
        if not name:
            flash(request, "Назва стікера не може бути порожньою.", "danger")
            return RedirectResponse("/admin/stickers", status_code=303)
        sticker.name = name
        sticker.color = color
        sticker.text_color = text_color
    flash(request, "Стікер оновлено.", "success")
    return RedirectResponse("/admin/stickers", status_code=303)


@admin_required
async def sticker_delete(request: Request):
    sticker_id = request.path_params["id"]
    with get_db() as db:
        sticker = db.get(Sticker, sticker_id)
        if sticker is None:
            flash(request, "Стікер не знайдено.", "danger")
            return RedirectResponse("/admin/stickers", status_code=303)
        name = sticker.name
        db.delete(sticker)
    flash(request, f"Стікер «{name}» видалено.", "success")
    return RedirectResponse("/admin/stickers", status_code=303)


routes = [
    Route("/admin/stickers", stickers_list, methods=["GET"]),
    Route("/admin/stickers/create", sticker_create, methods=["POST"]),
    Route("/admin/stickers/{id:int}/edit", sticker_edit, methods=["POST"]),
    Route("/admin/stickers/{id:int}/delete", sticker_delete, methods=["POST"]),
]
