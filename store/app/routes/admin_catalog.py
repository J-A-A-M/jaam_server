"""Адмін-маршрути: каталог — розділи, модифікації, товари."""

from __future__ import annotations

import decimal
import os
import uuid

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app.config import ALLOWED_IMAGE_EXT, MAX_IMAGE_BYTES, UPLOAD_DIR
from app.core import admin_required, flash
from app.db import get_db
from app.models import Category, Modification, ModificationValue, Product, ProductImage, Sticker
from app.templating import render

ZERO = decimal.Decimal("0.00")

# Whitelist content-type (на додачу до розширення) — захист від підміни типу.
_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _parse_decimal(raw: str | None) -> decimal.Decimal:
    return decimal.Decimal((raw or "0").replace(",", "."))


async def _save_upload(upload) -> str | None:
    """Безпечно зберігає завантажене фото. Повертає згенероване імʼя файла або None.

    Імʼя генерується (uuid) — НЕ довіряємо клієнтському (path traversal).
    Перевіряємо розширення + content-type + розмір.
    """
    original = getattr(upload, "filename", "") or ""
    ext = os.path.splitext(original)[1].lower()
    if ext not in ALLOWED_IMAGE_EXT:
        return None
    if (getattr(upload, "content_type", "") or "") not in _ALLOWED_CONTENT_TYPES:
        return None
    data = await upload.read()
    if not data or len(data) > MAX_IMAGE_BYTES:
        return None
    name = uuid.uuid4().hex + ext
    (UPLOAD_DIR / name).write_bytes(data)
    return name


# ===========================================================================
# A) РОЗДІЛИ (Category)
# ===========================================================================


@admin_required
async def categories_list(request: Request):
    with get_db() as db:
        roots = db.query(Category).filter_by(parent_id=None).all()
        all_cats = db.query(Category).order_by(Category.name).all()
        return render(
            request,
            "admin/categories.html",
            {"db": db, "roots": roots, "all_cats": all_cats},
        )


@admin_required
async def categories_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    pid = form.get("parent_id")
    parent_id = int(pid) if pid else None

    if not name:
        flash(request, "Назва розділу не може бути порожньою.", "danger")
        return RedirectResponse("/admin/categories", status_code=303)

    with get_db() as db:
        db.add(Category(name=name, parent_id=parent_id))
    flash(request, f"Розділ «{name}» створено.", "success")
    return RedirectResponse("/admin/categories", status_code=303)


@admin_required
async def categories_edit(request: Request):
    cat_id = request.path_params["id"]
    if request.method == "POST":
        form = await request.form()
        name = (form.get("name") or "").strip()
        pid = form.get("parent_id")
        parent_id = int(pid) if pid else None

        if not name:
            flash(request, "Назва розділу не може бути порожньою.", "danger")
            return RedirectResponse(f"/admin/categories/{cat_id}/edit", status_code=303)

        with get_db() as db:
            cat = db.get(Category, cat_id)
            if cat is None:
                flash(request, "Розділ не знайдено.", "danger")
                return RedirectResponse("/admin/categories", status_code=303)
            cat.name = name
            cat.parent_id = parent_id
        flash(request, "Розділ збережено.", "success")
        return RedirectResponse("/admin/categories", status_code=303)

    # GET
    with get_db() as db:
        cat = db.get(Category, cat_id)
        if cat is None:
            flash(request, "Розділ не знайдено.", "danger")
            return RedirectResponse("/admin/categories", status_code=303)
        # Виключаємо сам розділ зі списку доступних батьків
        all_cats = db.query(Category).filter(Category.id != cat_id).order_by(Category.name).all()
        return render(
            request,
            "admin/categories_edit.html",
            {"db": db, "cat": cat, "all_cats": all_cats},
        )


@admin_required
async def categories_delete(request: Request):
    cat_id = request.path_params["id"]
    with get_db() as db:
        cat = db.get(Category, cat_id)
        if cat is None:
            flash(request, "Розділ не знайдено.", "danger")
            return RedirectResponse("/admin/categories", status_code=303)
        name = cat.name
        db.delete(cat)
    flash(request, f"Розділ «{name}» видалено.", "success")
    return RedirectResponse("/admin/categories", status_code=303)


# ===========================================================================
# B) МОДИФІКАЦІЇ (Modification + ModificationValue)
# ===========================================================================


@admin_required
async def modifications_list(request: Request):
    with get_db() as db:
        mods = db.query(Modification).order_by(Modification.name).all()
        return render(request, "admin/modifications.html", {"db": db, "mods": mods})


@admin_required
async def modifications_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()

    if not name:
        flash(request, "Назва модифікації не може бути порожньою.", "danger")
        return RedirectResponse("/admin/modifications", status_code=303)

    with get_db() as db:
        db.add(Modification(name=name))
    flash(request, f"Модифікацію «{name}» створено.", "success")
    return RedirectResponse("/admin/modifications", status_code=303)


@admin_required
async def modifications_edit(request: Request):
    mod_id = request.path_params["id"]
    if request.method == "POST":
        form = await request.form()
        name = (form.get("name") or "").strip()

        if not name:
            flash(request, "Назва модифікації не може бути порожньою.", "danger")
            return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)

        with get_db() as db:
            mod = db.get(Modification, mod_id)
            if mod is None:
                flash(request, "Модифікацію не знайдено.", "danger")
                return RedirectResponse("/admin/modifications", status_code=303)
            mod.name = name
        flash(request, "Модифікацію збережено.", "success")
        return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)

    # GET
    with get_db() as db:
        mod = db.get(Modification, mod_id)
        if mod is None:
            flash(request, "Модифікацію не знайдено.", "danger")
            return RedirectResponse("/admin/modifications", status_code=303)
        return render(
            request,
            "admin/modifications_edit.html",
            {"db": db, "mod": mod},
        )


@admin_required
async def modifications_delete(request: Request):
    mod_id = request.path_params["id"]
    with get_db() as db:
        mod = db.get(Modification, mod_id)
        if mod is None:
            flash(request, "Модифікацію не знайдено.", "danger")
            return RedirectResponse("/admin/modifications", status_code=303)
        name = mod.name
        db.delete(mod)
    flash(request, f"Модифікацію «{name}» видалено.", "success")
    return RedirectResponse("/admin/modifications", status_code=303)


@admin_required
async def modification_values_add(request: Request):
    mod_id = request.path_params["id"]
    form = await request.form()
    label = (form.get("label") or "").strip()
    price = _parse_decimal(form.get("price"))
    is_custom_text = bool(form.get("is_custom_text"))

    if not label:
        flash(request, "Мітка значення не може бути порожньою.", "danger")
        return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)

    with get_db() as db:
        mod = db.get(Modification, mod_id)
        if mod is None:
            flash(request, "Модифікацію не знайдено.", "danger")
            return RedirectResponse("/admin/modifications", status_code=303)
        position = len(mod.values)
        db.add(
            ModificationValue(
                modification_id=mod_id,
                label=label,
                price=price,
                is_custom_text=is_custom_text,
                is_enabled=True,
                position=position,
            )
        )
    flash(request, f"Значення «{label}» додано.", "success")
    return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)


@admin_required
async def modification_value_update(request: Request):
    val_id = request.path_params["id"]
    form = await request.form()
    label = (form.get("label") or "").strip()
    price = _parse_decimal(form.get("price"))
    is_custom_text = bool(form.get("is_custom_text"))
    is_enabled = bool(form.get("is_enabled"))

    with get_db() as db:
        val = db.get(ModificationValue, val_id)
        if val is None:
            flash(request, "Значення не знайдено.", "danger")
            return RedirectResponse("/admin/modifications", status_code=303)
        mod_id = val.modification_id
        if label:
            val.label = label
        val.price = price
        val.is_custom_text = is_custom_text
        val.is_enabled = is_enabled
    flash(request, "Значення оновлено.", "success")
    return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)


@admin_required
async def modification_value_delete(request: Request):
    val_id = request.path_params["id"]
    with get_db() as db:
        val = db.get(ModificationValue, val_id)
        if val is None:
            flash(request, "Значення не знайдено.", "danger")
            return RedirectResponse("/admin/modifications", status_code=303)
        mod_id = val.modification_id
        db.delete(val)
    flash(request, "Значення видалено.", "success")
    return RedirectResponse(f"/admin/modifications/{mod_id}/edit", status_code=303)


# ===========================================================================
# C) ТОВАРИ (Product)
# ===========================================================================


@admin_required
async def products_list(request: Request):
    with get_db() as db:
        products = db.query(Product).order_by(Product.position, Product.name).all()
        all_cats = db.query(Category).order_by(Category.name).all()
        all_mods = db.query(Modification).order_by(Modification.name).all()
        return render(
            request,
            "admin/products.html",
            {"db": db, "products": products, "all_cats": all_cats, "all_mods": all_mods},
        )


@admin_required
async def products_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    description = (form.get("description") or "").strip()
    long_description = (form.get("long_description") or "").strip()
    base_price = _parse_decimal(form.get("base_price"))
    is_active = bool(form.get("is_active"))
    position = int(form.get("position") or 0)
    show_on_home = bool(form.get("show_on_home"))
    cat_ids = [int(x) for x in form.getlist("categories") if x]
    mod_ids = [int(x) for x in form.getlist("modifications") if x]
    sticker_ids = [int(x) for x in form.getlist("stickers") if x]

    if not name:
        flash(request, "Назва товару не може бути порожньою.", "danger")
        return RedirectResponse("/admin/products", status_code=303)

    with get_db() as db:
        cats = [db.get(Category, cid) for cid in cat_ids]
        cats = [c for c in cats if c is not None]
        mods = [db.get(Modification, mid) for mid in mod_ids]
        mods = [m for m in mods if m is not None]
        stickers = [db.get(Sticker, sid) for sid in sticker_ids]
        stickers = [s for s in stickers if s is not None]

        product = Product(
            name=name,
            description=description,
            long_description=long_description,
            base_price=base_price,
            is_active=is_active,
            position=position,
            show_on_home=show_on_home,
        )
        db.add(product)
        db.flush()
        product.categories = cats
        product.modifications = mods
        product.stickers = stickers

    flash(request, f"Товар «{name}» створено.", "success")
    return RedirectResponse("/admin/products", status_code=303)


@admin_required
async def products_edit(request: Request):
    product_id = request.path_params["id"]
    if request.method == "POST":
        form = await request.form()
        name = (form.get("name") or "").strip()
        description = (form.get("description") or "").strip()
        long_description = (form.get("long_description") or "").strip()
        base_price = _parse_decimal(form.get("base_price"))
        is_active = bool(form.get("is_active"))
        position = int(form.get("position") or 0)
        show_on_home = bool(form.get("show_on_home"))
        cat_ids = [int(x) for x in form.getlist("categories") if x]
        mod_ids = [int(x) for x in form.getlist("modifications") if x]
        sticker_ids = [int(x) for x in form.getlist("stickers") if x]

        if not name:
            flash(request, "Назва товару не може бути порожньою.", "danger")
            return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)

        with get_db() as db:
            product = db.get(Product, product_id)
            if product is None:
                flash(request, "Товар не знайдено.", "danger")
                return RedirectResponse("/admin/products", status_code=303)

            cats = [db.get(Category, cid) for cid in cat_ids]
            cats = [c for c in cats if c is not None]
            mods = [db.get(Modification, mid) for mid in mod_ids]
            mods = [m for m in mods if m is not None]
            stickers = [db.get(Sticker, sid) for sid in sticker_ids]
            stickers = [s for s in stickers if s is not None]

            product.name = name
            product.description = description
            product.long_description = long_description
            product.base_price = base_price
            product.is_active = is_active
            product.position = position
            product.show_on_home = show_on_home
            product.categories = cats
            product.modifications = mods
            product.stickers = stickers

        flash(request, "Товар збережено.", "success")
        return RedirectResponse("/admin/products", status_code=303)

    # GET
    with get_db() as db:
        product = db.get(Product, product_id)
        if product is None:
            flash(request, "Товар не знайдено.", "danger")
            return RedirectResponse("/admin/products", status_code=303)
        all_cats = db.query(Category).order_by(Category.name).all()
        all_mods = db.query(Modification).order_by(Modification.name).all()
        all_stickers = db.query(Sticker).order_by(Sticker.name).all()
        selected_cat_ids = {c.id for c in product.categories}
        selected_mod_ids = {m.id for m in product.modifications}
        selected_sticker_ids = {s.id for s in product.stickers}
        return render(
            request,
            "admin/products_edit.html",
            {
                "db": db,
                "product": product,
                "all_cats": all_cats,
                "all_mods": all_mods,
                "all_stickers": all_stickers,
                "selected_cat_ids": selected_cat_ids,
                "selected_mod_ids": selected_mod_ids,
                "selected_sticker_ids": selected_sticker_ids,
            },
        )


@admin_required
async def product_images_add(request: Request):
    product_id = request.path_params["id"]
    form = await request.form()
    uploads = form.getlist("images")
    saved, rejected = 0, 0
    with get_db() as db:
        product = db.get(Product, product_id)
        if product is None:
            flash(request, "Товар не знайдено.", "danger")
            return RedirectResponse("/admin/products", status_code=303)
        position = len(product.images)
        for up in uploads:
            if not getattr(up, "filename", ""):
                continue
            name = await _save_upload(up)
            if name is None:
                rejected += 1
                continue
            db.add(ProductImage(product_id=product_id, filename=name, position=position))
            position += 1
            saved += 1
    if saved:
        flash(request, f"Додано фото: {saved}.", "success")
    if rejected:
        flash(request, f"Відхилено файлів (тип/розмір): {rejected}.", "warning")
    if not saved and not rejected:
        flash(request, "Файли не вибрано.", "warning")
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@admin_required
async def product_image_delete(request: Request):
    image_id = request.path_params["id"]
    with get_db() as db:
        img = db.get(ProductImage, image_id)
        if img is None:
            flash(request, "Фото не знайдено.", "danger")
            return RedirectResponse("/admin/products", status_code=303)
        product_id = img.product_id
        fname = os.path.basename(img.filename)  # захист від path traversal
        db.delete(img)
    try:
        (UPLOAD_DIR / fname).unlink(missing_ok=True)
    except OSError:
        pass
    flash(request, "Фото видалено.", "success")
    return RedirectResponse(f"/admin/products/{product_id}/edit", status_code=303)


@admin_required
async def products_delete(request: Request):
    product_id = request.path_params["id"]
    with get_db() as db:
        product = db.get(Product, product_id)
        if product is None:
            flash(request, "Товар не знайдено.", "danger")
            return RedirectResponse("/admin/products", status_code=303)
        name = product.name
        db.delete(product)
    flash(request, f"Товар «{name}» видалено.", "success")
    return RedirectResponse("/admin/products", status_code=303)


# ===========================================================================
# Маршрути
# ===========================================================================
routes = [
    # Розділи
    Route("/admin/categories", categories_list, methods=["GET"]),
    Route("/admin/categories/create", categories_create, methods=["POST"]),
    Route("/admin/categories/{id:int}/edit", categories_edit, methods=["GET", "POST"]),
    Route("/admin/categories/{id:int}/delete", categories_delete, methods=["POST"]),
    # Модифікації
    Route("/admin/modifications", modifications_list, methods=["GET"]),
    Route("/admin/modifications/create", modifications_create, methods=["POST"]),
    Route("/admin/modifications/{id:int}/edit", modifications_edit, methods=["GET", "POST"]),
    Route("/admin/modifications/{id:int}/delete", modifications_delete, methods=["POST"]),
    Route("/admin/modifications/{id:int}/values/add", modification_values_add, methods=["POST"]),
    Route("/admin/modification_values/{id:int}/update", modification_value_update, methods=["POST"]),
    Route("/admin/modification_values/{id:int}/delete", modification_value_delete, methods=["POST"]),
    # Товари
    Route("/admin/products", products_list, methods=["GET"]),
    Route("/admin/products/create", products_create, methods=["POST"]),
    Route("/admin/products/{id:int}/edit", products_edit, methods=["GET", "POST"]),
    Route("/admin/products/{id:int}/delete", products_delete, methods=["POST"]),
    Route("/admin/products/{id:int}/images/add", product_images_add, methods=["POST"]),
    Route("/admin/product_images/{id:int}/delete", product_image_delete, methods=["POST"]),
]
