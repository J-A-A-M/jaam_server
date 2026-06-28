"""Адмін-маршрути: дашборд, адміни, ключі доступу."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app.config import MASTER_KEY
from app.core import admin_required, current_user, flash, generate_admin_key, login_required
from app.db import get_db
from app.models import AdminKey, Category, Order, Product, User
from app.templating import render


# ===========================================================================
# 1) GET /admin — дашборд
# ===========================================================================
@admin_required
async def dashboard(request: Request):
    with get_db() as db:
        products_count = db.query(Product).count()
        categories_count = db.query(Category).count()
        orders_count = db.query(Order).count()
        admins_count = db.query(User).filter_by(is_admin=True).count()
        return render(
            request,
            "admin/dashboard.html",
            {
                "db": db,
                "products_count": products_count,
                "categories_count": categories_count,
                "orders_count": orders_count,
                "admins_count": admins_count,
            },
        )


# ===========================================================================
# 2) GET+POST /admin/become — стати адміном
# ===========================================================================
@login_required
async def become_admin(request: Request):
    if request.method == "POST":
        form = await request.form()
        key = (form.get("key") or "").strip()

        with get_db() as db:
            user = current_user(request, db)

            # Порожній MASTER_KEY = вхід за майстер-ключем вимкнено.
            # compare_digest — захист від timing-атак.
            if MASTER_KEY and key and secrets.compare_digest(key, MASTER_KEY):
                user.is_admin = True
                flash(request, "Ви стали адміністратором (майстер-ключ).", "success")
                return RedirectResponse("/admin", status_code=303)

            ak = db.query(AdminKey).filter_by(key=key, used=False).first()
            if ak is not None:
                ak.used = True
                ak.used_by_id = user.id
                ak.used_at = datetime.now(timezone.utc)
                user.is_admin = True
                flash(request, "Ви стали адміністратором.", "success")
                return RedirectResponse("/admin", status_code=303)

            flash(request, "Невірний або вже використаний ключ.", "danger")
            return RedirectResponse("/admin/become", status_code=303)

    # GET
    with get_db() as db:
        return render(request, "admin/become.html", {"db": db})


# ===========================================================================
# 3) GET /admin/admins — список адмінів
# ===========================================================================
@admin_required
async def admins_list(request: Request):
    with get_db() as db:
        admins = db.query(User).filter_by(is_admin=True).order_by(User.created_at).all()
        me = current_user(request, db)
        return render(
            request,
            "admin/admins.html",
            {
                "db": db,
                "admins": admins,
                "me_id": me.id if me else None,
            },
        )


# ===========================================================================
# 4) POST /admin/admins/{id:int}/revoke — зняти права адміна
# ===========================================================================
@admin_required
async def revoke_admin(request: Request):
    target_id = request.path_params["id"]
    with get_db() as db:
        me = current_user(request, db)
        if me and me.id == target_id:
            flash(request, "Неможливо зняти права адміністратора з самого себе.", "warning")
            return RedirectResponse("/admin/admins", status_code=303)

        target = db.get(User, target_id)
        if target is None:
            flash(request, "Користувача не знайдено.", "danger")
            return RedirectResponse("/admin/admins", status_code=303)

        target.is_admin = False
        flash(request, f"Права адміністратора знято з {target.email}.", "success")
        return RedirectResponse("/admin/admins", status_code=303)


# ===========================================================================
# 5) GET /admin/keys — список ключів
# ===========================================================================
@admin_required
async def keys_list(request: Request):
    with get_db() as db:
        keys = db.query(AdminKey).order_by(AdminKey.created_at.desc()).all()
        return render(
            request,
            "admin/keys.html",
            {
                "db": db,
                "keys": keys,
            },
        )


# ===========================================================================
# 6) POST /admin/keys/generate — згенерувати новий ключ
# ===========================================================================
@admin_required
async def keys_generate(request: Request):
    with get_db() as db:
        me = current_user(request, db)
        new_key = generate_admin_key(db, me)
        flash(request, f"Новий ключ: {new_key}", "success")
        return RedirectResponse("/admin/keys", status_code=303)


# ===========================================================================
# 7) Користувачі + постійна знижка акаунта
# ===========================================================================
@admin_required
async def users_list(request: Request):
    with get_db() as db:
        users = db.query(User).order_by(User.created_at).all()
        return render(request, "admin/users.html", {"db": db, "users": users})


@admin_required
async def user_set_discount(request: Request):
    import decimal

    uid = request.path_params["id"]
    form = await request.form()
    raw = (form.get("discount_percent") or "0").replace(",", ".").strip()
    with get_db() as db:
        u = db.get(User, uid)
        if u is None:
            flash(request, "Користувача не знайдено.", "danger")
            return RedirectResponse("/admin/users", status_code=303)
        try:
            pct = decimal.Decimal(raw)
        except (decimal.InvalidOperation, ValueError):
            pct = decimal.Decimal("0")
        pct = max(decimal.Decimal("0"), min(decimal.Decimal("100"), pct))
        u.discount_percent = pct
        flash(request, f"Знижку для {u.email} встановлено: {pct}%.", "success")
    return RedirectResponse("/admin/users", status_code=303)


# ===========================================================================
# Маршрути
# ===========================================================================
routes = [
    Route("/admin", dashboard, methods=["GET"]),
    Route("/admin/become", become_admin, methods=["GET", "POST"]),
    Route("/admin/admins", admins_list, methods=["GET"]),
    Route("/admin/admins/{id:int}/revoke", revoke_admin, methods=["POST"]),
    Route("/admin/users", users_list, methods=["GET"]),
    Route("/admin/users/{id:int}/discount", user_set_discount, methods=["POST"]),
    Route("/admin/keys", keys_list, methods=["GET"]),
    Route("/admin/keys/generate", keys_generate, methods=["POST"]),
]
