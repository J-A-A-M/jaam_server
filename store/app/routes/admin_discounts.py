"""Адмін-маршрути: коди знижок."""

from __future__ import annotations

import decimal
from datetime import datetime

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app.core import admin_required, current_user, flash, generate_discount_code
from app.db import get_db
from app.models import DISCOUNT_AMOUNT, DISCOUNT_PERCENT, DiscountCode
from app.templating import render

# ---------------------------------------------------------------------------
# Хелпери
# ---------------------------------------------------------------------------


def parse_expires(raw: str | None) -> datetime | None:
    """Парсить рядок datetime-local у наївний datetime (UTC без tzinfo)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None


def _parse_value(raw: str | None) -> decimal.Decimal:
    try:
        return decimal.Decimal((raw or "0").replace(",", "."))
    except decimal.InvalidOperation:
        return decimal.Decimal("0")


# ===========================================================================
# 1) GET /admin/discounts — список кодів + форма створення
# ===========================================================================


@admin_required
async def discounts_list(request: Request):
    with get_db() as db:
        codes = db.query(DiscountCode).order_by(DiscountCode.created_at.desc()).all()
        return render(
            request,
            "admin/discounts.html",
            {
                "db": db,
                "codes": codes,
                "DISCOUNT_PERCENT": DISCOUNT_PERCENT,
                "DISCOUNT_AMOUNT": DISCOUNT_AMOUNT,
            },
        )


# ===========================================================================
# 2) POST /admin/discounts/create — створити код
# ===========================================================================


@admin_required
async def discount_create(request: Request):
    form = await request.form()

    with get_db() as db:
        # --- код ---
        code_str = (form.get("code") or "").strip().upper()
        if code_str:
            # перевірити унікальність введеного коду
            if db.query(DiscountCode).filter_by(code=code_str).first():
                flash(request, f"Код «{code_str}» вже існує.", "danger")
                return RedirectResponse("/admin/discounts", status_code=303)
        else:
            # авто-генерація з перевіркою на унікальність
            for _ in range(10):
                code_str = generate_discount_code()
                if not db.query(DiscountCode).filter_by(code=code_str).first():
                    break

        # --- тип ---
        kind = form.get("kind")
        if kind not in (DISCOUNT_PERCENT, DISCOUNT_AMOUNT):
            kind = DISCOUNT_PERCENT

        # --- значення ---
        value = _parse_value(form.get("value"))
        if value < decimal.Decimal("0"):
            value = decimal.Decimal("0")
        if kind == DISCOUNT_PERCENT and value > decimal.Decimal("100"):
            value = decimal.Decimal("100")

        # --- ліміт активацій ---
        max_activations = max(0, int(form.get("max_activations") or 0))

        # --- термін дії ---
        expires_at = parse_expires(form.get("expires_at"))

        # --- активний ---
        is_active = bool(form.get("is_active"))

        # --- автор ---
        user = current_user(request, db)
        created_by_id = user.id if user else None

        code_obj = DiscountCode(
            code=code_str,
            kind=kind,
            value=value,
            max_activations=max_activations,
            expires_at=expires_at,
            is_active=is_active,
            created_by_id=created_by_id,
        )
        db.add(code_obj)

    flash(request, f"Код знижки «{code_str}» створено.", "success")
    return RedirectResponse("/admin/discounts", status_code=303)


# ===========================================================================
# 3) GET /admin/discounts/{id:int} — деталі коду + форма редагування + лог
# ===========================================================================


@admin_required
async def discount_detail(request: Request):
    code_id = request.path_params["id"]
    with get_db() as db:
        code = db.get(DiscountCode, code_id)
        if code is None:
            flash(request, "Код знижки не знайдено.", "danger")
            return RedirectResponse("/admin/discounts", status_code=303)
        return render(
            request,
            "admin/discount_detail.html",
            {
                "db": db,
                "code": code,
                "DISCOUNT_PERCENT": DISCOUNT_PERCENT,
                "DISCOUNT_AMOUNT": DISCOUNT_AMOUNT,
            },
        )


# ===========================================================================
# 4) POST /admin/discounts/{id:int}/edit — оновити код
# ===========================================================================


@admin_required
async def discount_edit(request: Request):
    code_id = request.path_params["id"]
    form = await request.form()

    with get_db() as db:
        code = db.get(DiscountCode, code_id)
        if code is None:
            flash(request, "Код знижки не знайдено.", "danger")
            return RedirectResponse("/admin/discounts", status_code=303)

        kind = form.get("kind")
        if kind not in (DISCOUNT_PERCENT, DISCOUNT_AMOUNT):
            kind = DISCOUNT_PERCENT

        value = _parse_value(form.get("value"))
        if value < decimal.Decimal("0"):
            value = decimal.Decimal("0")
        if kind == DISCOUNT_PERCENT and value > decimal.Decimal("100"):
            value = decimal.Decimal("100")

        code.kind = kind
        code.value = value
        code.max_activations = max(0, int(form.get("max_activations") or 0))
        code.expires_at = parse_expires(form.get("expires_at"))
        code.is_active = bool(form.get("is_active"))

    flash(request, "Код знижки оновлено.", "success")
    return RedirectResponse(f"/admin/discounts/{code_id}", status_code=303)


# ===========================================================================
# 5) POST /admin/discounts/{id:int}/toggle — увімкнути/вимкнути
# ===========================================================================


@admin_required
async def discount_toggle(request: Request):
    code_id = request.path_params["id"]
    with get_db() as db:
        code = db.get(DiscountCode, code_id)
        if code is None:
            flash(request, "Код знижки не знайдено.", "danger")
            return RedirectResponse("/admin/discounts", status_code=303)
        code.is_active = not code.is_active
        state = "активовано" if code.is_active else "вимкнено"

    flash(request, f"Код знижки {state}.", "success")
    return RedirectResponse(f"/admin/discounts/{code_id}", status_code=303)


# ===========================================================================
# 6) POST /admin/discounts/{id:int}/delete — видалити код
# ===========================================================================


@admin_required
async def discount_delete(request: Request):
    code_id = request.path_params["id"]
    with get_db() as db:
        code = db.get(DiscountCode, code_id)
        if code is None:
            flash(request, "Код знижки не знайдено.", "danger")
            return RedirectResponse("/admin/discounts", status_code=303)
        label = code.code
        db.delete(code)

    flash(request, f"Код знижки «{label}» видалено.", "success")
    return RedirectResponse("/admin/discounts", status_code=303)


# ===========================================================================
# Маршрути
# ===========================================================================

routes = [
    Route("/admin/discounts", discounts_list, methods=["GET"]),
    Route("/admin/discounts/create", discount_create, methods=["POST"]),
    Route("/admin/discounts/{id:int}", discount_detail, methods=["GET"]),
    Route("/admin/discounts/{id:int}/edit", discount_edit, methods=["POST"]),
    Route("/admin/discounts/{id:int}/toggle", discount_toggle, methods=["POST"]),
    Route("/admin/discounts/{id:int}/delete", discount_delete, methods=["POST"]),
]
