"""Адмін-маршрути: знижки на товар (ProductDiscount)."""

from __future__ import annotations

import decimal
from datetime import datetime

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app.core import admin_required, flash
from app.db import get_db
from app.models import (
    DISCOUNT_AMOUNT,
    DISCOUNT_PERCENT,
    DISCOUNT_SCOPE_BASE,
    DISCOUNT_SCOPE_FULL,
    Product,
    ProductDiscount,
    Sticker,
)
from app.templating import render


def _parse_value(raw: str | None) -> decimal.Decimal:
    try:
        return decimal.Decimal((raw or "0").replace(",", "."))
    except decimal.InvalidOperation:
        return decimal.Decimal("0")


def _parse_expires(raw: str | None) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def _read_form(form) -> dict:
    kind = form.get("kind")
    if kind not in (DISCOUNT_PERCENT, DISCOUNT_AMOUNT):
        kind = DISCOUNT_PERCENT
    scope = form.get("scope")
    if scope not in (DISCOUNT_SCOPE_BASE, DISCOUNT_SCOPE_FULL):
        scope = DISCOUNT_SCOPE_FULL
    value = _parse_value(form.get("value"))
    if value < decimal.Decimal("0"):
        value = decimal.Decimal("0")
    if kind == DISCOUNT_PERCENT and value > decimal.Decimal("100"):
        value = decimal.Decimal("100")
    sticker_raw = (form.get("sticker_id") or "").strip()
    sticker_id = int(sticker_raw) if sticker_raw else None
    return {
        "name": (form.get("name") or "").strip(),
        "kind": kind,
        "scope": scope,
        "value": value,
        "max_orders": max(0, int(form.get("max_orders") or 0)),
        "starts_at": _parse_expires(form.get("starts_at")),
        "expires_at": _parse_expires(form.get("expires_at")),
        "is_active": bool(form.get("is_active")),
        "stack_account": bool(form.get("stack_account")),
        "stack_code": bool(form.get("stack_code")),
        "sticker_id": sticker_id,
    }


@admin_required
async def discounts_list(request: Request):
    with get_db() as db:
        discounts = db.query(ProductDiscount).order_by(ProductDiscount.created_at.desc()).all()
        all_stickers = db.query(Sticker).order_by(Sticker.name).all()
        return render(
            request,
            "admin/product_discounts.html",
            {
                "db": db,
                "discounts": discounts,
                "all_stickers": all_stickers,
                "DISCOUNT_PERCENT": DISCOUNT_PERCENT,
                "DISCOUNT_AMOUNT": DISCOUNT_AMOUNT,
            },
        )


@admin_required
async def discount_create(request: Request):
    form = await request.form()
    data = _read_form(form)
    if not data["name"]:
        flash(request, "Назва знижки не може бути порожньою.", "danger")
        return RedirectResponse("/admin/product-discounts", status_code=303)
    with get_db() as db:
        db.add(ProductDiscount(**data))
    flash(request, f"Знижку «{data['name']}» створено.", "success")
    return RedirectResponse("/admin/product-discounts", status_code=303)


@admin_required
async def discount_detail(request: Request):
    discount_id = request.path_params["id"]
    with get_db() as db:
        discount = db.get(ProductDiscount, discount_id)
        if discount is None:
            flash(request, "Знижку не знайдено.", "danger")
            return RedirectResponse("/admin/product-discounts", status_code=303)
        all_products = db.query(Product).order_by(Product.name).all()
        all_stickers = db.query(Sticker).order_by(Sticker.name).all()
        selected_ids = {p.id for p in discount.products}
        return render(
            request,
            "admin/product_discount_detail.html",
            {
                "db": db,
                "discount": discount,
                "all_products": all_products,
                "all_stickers": all_stickers,
                "selected_ids": selected_ids,
                "DISCOUNT_PERCENT": DISCOUNT_PERCENT,
                "DISCOUNT_AMOUNT": DISCOUNT_AMOUNT,
                "DISCOUNT_SCOPE_BASE": DISCOUNT_SCOPE_BASE,
                "DISCOUNT_SCOPE_FULL": DISCOUNT_SCOPE_FULL,
            },
        )


@admin_required
async def discount_edit(request: Request):
    discount_id = request.path_params["id"]
    form = await request.form()
    data = _read_form(form)
    product_ids = [int(x) for x in form.getlist("products") if x]
    with get_db() as db:
        discount = db.get(ProductDiscount, discount_id)
        if discount is None:
            flash(request, "Знижку не знайдено.", "danger")
            return RedirectResponse("/admin/product-discounts", status_code=303)
        if not data["name"]:
            flash(request, "Назва знижки не може бути порожньою.", "danger")
            return RedirectResponse(f"/admin/product-discounts/{discount_id}", status_code=303)
        for k, v in data.items():
            setattr(discount, k, v)
        products = [db.get(Product, pid) for pid in product_ids]
        discount.products = [p for p in products if p is not None]
    flash(request, "Знижку оновлено.", "success")
    return RedirectResponse(f"/admin/product-discounts/{discount_id}", status_code=303)


@admin_required
async def discount_toggle(request: Request):
    discount_id = request.path_params["id"]
    with get_db() as db:
        discount = db.get(ProductDiscount, discount_id)
        if discount is None:
            flash(request, "Знижку не знайдено.", "danger")
            return RedirectResponse("/admin/product-discounts", status_code=303)
        discount.is_active = not discount.is_active
        state = "активовано" if discount.is_active else "вимкнено"
    flash(request, f"Знижку {state}.", "success")
    return RedirectResponse(f"/admin/product-discounts/{discount_id}", status_code=303)


@admin_required
async def discount_delete(request: Request):
    discount_id = request.path_params["id"]
    with get_db() as db:
        discount = db.get(ProductDiscount, discount_id)
        if discount is None:
            flash(request, "Знижку не знайдено.", "danger")
            return RedirectResponse("/admin/product-discounts", status_code=303)
        name = discount.name
        db.delete(discount)
    flash(request, f"Знижку «{name}» видалено.", "success")
    return RedirectResponse("/admin/product-discounts", status_code=303)


routes = [
    Route("/admin/product-discounts", discounts_list, methods=["GET"]),
    Route("/admin/product-discounts/create", discount_create, methods=["POST"]),
    Route("/admin/product-discounts/{id:int}", discount_detail, methods=["GET"]),
    Route("/admin/product-discounts/{id:int}/edit", discount_edit, methods=["POST"]),
    Route("/admin/product-discounts/{id:int}/toggle", discount_toggle, methods=["POST"]),
    Route("/admin/product-discounts/{id:int}/delete", discount_delete, methods=["POST"]),
]
