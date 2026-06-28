"""Адмін-маршрути: замовлення, статуси, flow переходів."""

from __future__ import annotations

from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.routing import Route

from app import nova_poshta
from app.core import admin_required, available_transitions, build_waybill_description, flash, move_order
from app.db import STATUS_CANCELLED, get_db
from app.models import Order, OrderStatus, StatusTransition
from app.np_settings import load_np
from app.templating import render


# ===========================================================================
# 1) GET /admin/orders — список усіх замовлень
# ===========================================================================
@admin_required
async def orders_list(request: Request):
    with get_db() as db:
        orders = db.query(Order).order_by(Order.created_at.desc()).all()
        return render(request, "admin/orders.html", {"db": db, "orders": orders})


# ===========================================================================
# 2) GET /admin/orders/{id:int} — деталі замовлення
# ===========================================================================
@admin_required
async def order_detail(request: Request):
    order_id = request.path_params["id"]
    with get_db() as db:
        order = db.get(Order, order_id)
        if order is None:
            flash(request, "Замовлення не знайдено.", "danger")
            return RedirectResponse("/admin/orders", status_code=303)
        targets = available_transitions(db, order)
        cfg = load_np()  # ефективні налаштування (БД -> env)
        return render(
            request,
            "admin/order_detail.html",
            {
                "db": db,
                "order": order,
                "targets": targets,
                "STATUS_CANCELLED": STATUS_CANCELLED,
                "np_enabled": bool(cfg.api_key),
                "default_description": build_waybill_description(order),
                "np_default_weight": cfg.default_weight,
                "np_default_width": cfg.seat_width,
                "np_default_length": cfg.seat_length,
                "np_default_height": cfg.seat_height,
            },
        )


# ===========================================================================
# Формування експрес-накладної (ЕН) Нова Пошта
# ===========================================================================
@admin_required
async def order_waybill(request: Request):
    order_id = request.path_params["id"]
    form = await request.form()
    weight = (form.get("weight") or "").strip()
    width = (form.get("width") or "").strip()
    length = (form.get("length") or "").strip()
    height = (form.get("height") or "").strip()
    description = (form.get("description") or "").strip()
    with get_db() as db:
        order = db.get(Order, order_id)
        if order is None:
            flash(request, "Замовлення не знайдено.", "danger")
            return RedirectResponse("/admin/orders", status_code=303)
        if order.np_waybill_number:
            flash(request, f"ЕН вже створено: {order.np_waybill_number}.", "warning")
            return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)
        # Зчитуємо потрібні дані до виходу із сесії (виклик API — поза транзакцією).
        data = {
            "full_name": order.full_name,
            "phone": order.recipient_phone or (order.user.phone if order.user else ""),
            "city_ref": order.np_city_ref,
            "warehouse_ref": order.np_warehouse_ref,
            "cost": order.total_price,
            "description": description or build_waybill_description(order),
            "internal_number": str(order.number or order.id),
        }

    try:
        result = await nova_poshta.create_waybill(weight=weight, width=width, length=length, height=height, **data)
    except nova_poshta.NovaPoshtaError as e:
        flash(request, f"Помилка Нова Пошта: {e}", "danger")
        return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)

    with get_db() as db:
        order = db.get(Order, order_id)
        order.np_waybill_number = result["number"]
        order.np_waybill_ref = result["ref"]
        flash(request, f"ЕН створено: {result['number']}.", "success")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


# ===========================================================================
# 3) POST /admin/orders/{id:int}/move — перевести замовлення в інший статус
# ===========================================================================
@admin_required
async def order_move(request: Request):
    order_id = request.path_params["id"]
    form = await request.form()
    target_status_id = int(form["target_status_id"])
    with get_db() as db:
        order = db.get(Order, order_id)
        if order is None:
            flash(request, "Замовлення не знайдено.", "danger")
            return RedirectResponse("/admin/orders", status_code=303)
        if move_order(db, order, target_status_id):
            flash(request, "Статус замовлення оновлено.", "success")
        else:
            flash(request, "Недозволений перехід.", "danger")
    return RedirectResponse(f"/admin/orders/{order_id}", status_code=303)


# ===========================================================================
# 4) GET /admin/statuses — список статусів та flow переходів
# ===========================================================================
@admin_required
async def statuses_page(request: Request):
    with get_db() as db:
        statuses = db.query(OrderStatus).order_by(OrderStatus.position).all()
        transitions = db.query(StatusTransition).join(StatusTransition.from_status).order_by(OrderStatus.position).all()
        return render(
            request,
            "admin/statuses.html",
            {
                "db": db,
                "statuses": statuses,
                "transitions": transitions,
            },
        )


# ===========================================================================
# 5) POST /admin/statuses/create — створити новий статус
# ===========================================================================
@admin_required
async def status_create(request: Request):
    form = await request.form()
    name = (form.get("name") or "").strip()
    position = int(form.get("position") or 0)
    color = (form.get("color") or "#007bff").strip()
    text_color = (form.get("text_color") or "#ffffff").strip()
    with get_db() as db:
        if not name:
            flash(request, "Назва статусу не може бути порожньою.", "warning")
            return RedirectResponse("/admin/statuses", status_code=303)
        existing = db.query(OrderStatus).filter_by(name=name).first()
        if existing:
            flash(request, f"Статус «{name}» вже існує.", "danger")
            return RedirectResponse("/admin/statuses", status_code=303)
        db.add(OrderStatus(name=name, is_fixed=False, position=position, color=color, text_color=text_color))
        flash(request, f"Статус «{name}» створено.", "success")
    return RedirectResponse("/admin/statuses", status_code=303)


# ===========================================================================
# 6) POST /admin/statuses/{id:int}/edit — перейменувати/змінити позицію
# ===========================================================================
@admin_required
async def status_edit(request: Request):
    status_id = request.path_params["id"]
    form = await request.form()
    name = (form.get("name") or "").strip()
    position = int(form.get("position") or 0)
    color = (form.get("color") or "#007bff").strip()
    text_color = (form.get("text_color") or "#ffffff").strip()
    with get_db() as db:
        status = db.get(OrderStatus, status_id)
        if status is None:
            flash(request, "Статус не знайдено.", "danger")
            return RedirectResponse("/admin/statuses", status_code=303)
        if not name:
            flash(request, "Назва статусу не може бути порожньою.", "warning")
            return RedirectResponse("/admin/statuses", status_code=303)
        status.name = name
        status.position = position
        status.color = color
        status.text_color = text_color
        flash(request, f"Статус оновлено до «{name}».", "success")
    return RedirectResponse("/admin/statuses", status_code=303)


# ===========================================================================
# 7) POST /admin/statuses/{id:int}/delete — видалити статус
# ===========================================================================
@admin_required
async def status_delete(request: Request):
    status_id = request.path_params["id"]
    with get_db() as db:
        status = db.get(OrderStatus, status_id)
        if status is None:
            flash(request, "Статус не знайдено.", "danger")
            return RedirectResponse("/admin/statuses", status_code=303)
        if status.is_fixed:
            flash(request, "Фіксований статус видалити не можна.", "warning")
            return RedirectResponse("/admin/statuses", status_code=303)
        name = status.name
        db.delete(status)
        flash(request, f"Статус «{name}» видалено.", "success")
    return RedirectResponse("/admin/statuses", status_code=303)


# ===========================================================================
# 8) POST /admin/transitions/create — додати перехід
# ===========================================================================
@admin_required
async def transition_create(request: Request):
    form = await request.form()
    from_id = int(form["from_status_id"])
    to_id = int(form["to_status_id"])
    with get_db() as db:
        if from_id == to_id:
            flash(request, "Статус-джерело і статус-ціль мають бути різними.", "warning")
            return RedirectResponse("/admin/statuses", status_code=303)
        existing = db.query(StatusTransition).filter_by(from_status_id=from_id, to_status_id=to_id).first()
        if existing:
            flash(request, "Такий перехід вже існує.", "danger")
            return RedirectResponse("/admin/statuses", status_code=303)
        db.add(StatusTransition(from_status_id=from_id, to_status_id=to_id))
        flash(request, "Перехід додано.", "success")
    return RedirectResponse("/admin/statuses", status_code=303)


# ===========================================================================
# 9) POST /admin/transitions/{id:int}/delete — видалити перехід
# ===========================================================================
@admin_required
async def transition_delete(request: Request):
    transition_id = request.path_params["id"]
    with get_db() as db:
        transition = db.get(StatusTransition, transition_id)
        if transition is None:
            flash(request, "Перехід не знайдено.", "danger")
            return RedirectResponse("/admin/statuses", status_code=303)
        db.delete(transition)
        flash(request, "Перехід видалено.", "success")
    return RedirectResponse("/admin/statuses", status_code=303)


# ===========================================================================
# Маршрути
# ===========================================================================
routes = [
    Route("/admin/orders", orders_list, methods=["GET"]),
    Route("/admin/orders/{id:int}", order_detail, methods=["GET"]),
    Route("/admin/orders/{id:int}/move", order_move, methods=["POST"]),
    Route("/admin/orders/{id:int}/waybill", order_waybill, methods=["POST"]),
    Route("/admin/statuses", statuses_page, methods=["GET"]),
    Route("/admin/statuses/create", status_create, methods=["POST"]),
    Route("/admin/statuses/{id:int}/edit", status_edit, methods=["POST"]),
    Route("/admin/statuses/{id:int}/delete", status_delete, methods=["POST"]),
    Route("/admin/transitions/create", transition_create, methods=["POST"]),
    Route("/admin/transitions/{id:int}/delete", transition_delete, methods=["POST"]),
]
