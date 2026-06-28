"""Спільна бізнес-логіка (КОНТРАКТ для всіх route-модулів).

Тут живе те, що НЕ можна дублювати в окремих модулях:
  - автентифікація / сесія / декоратори доступу
  - кошик у cookie-сесії
  - розрахунок ціни на сервері (єдине джерело правди)
  - створення замовлення з кошика
  - state-machine flow статусів

Route-модулі ІМПОРТУЮТЬ ці хелпери, а не переписують їх.
"""

from __future__ import annotations

import decimal
import functools
import secrets
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import RedirectResponse

from app.db import (
    ROLE_CANCELLED,
    ROLE_NEW,
    STATUS_CANCELLED,
    STATUS_NEW,
)
from app.models import (
    DISCOUNT_AMOUNT,
    DISCOUNT_PERCENT,
    DISCOUNT_SCOPE_BASE,
    DiscountActivation,
    DiscountCode,
    ModificationValue,
    Order,
    OrderItem,
    OrderItemModification,
    OrderStatus,
    OrderStatusLog,
    Product,
    ProductDiscount,
    User,
)

ZERO = decimal.Decimal("0.00")


def money(value) -> decimal.Decimal:
    return decimal.Decimal(value).quantize(decimal.Decimal("0.01"))


# ===========================================================================
#  Сесія / автентифікація
# ===========================================================================
def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.pop("user_id", None)


def current_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("user_id")
    if uid is None:
        return None
    return db.get(User, uid)


def flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flashes", []).append({"msg": message, "cat": category})


def pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


# --- Декоратори доступу для async-ендпоінтів --------------------------------
# Використання:
#     @login_required
#     async def view(request): ...
# Усередині відкривайте власну сесію БД через `with get_db() as db:`.
def login_required(func):
    @functools.wraps(func)
    async def wrapper(request: Request):
        if request.session.get("user_id") is None:
            flash(request, "Спочатку увійдіть у систему.", "warning")
            return RedirectResponse(url=f"/login?next={request.url.path}", status_code=303)
        return await func(request)

    return wrapper


def admin_required(func):
    @functools.wraps(func)
    async def wrapper(request: Request):
        from app.db import get_db

        with get_db() as db:
            user = current_user(request, db)
            if user is None:
                flash(request, "Спочатку увійдіть у систему.", "warning")
                return RedirectResponse(url="/login", status_code=303)
            if not user.is_admin:
                flash(request, "Потрібні права адміністратора.", "danger")
                return RedirectResponse(url="/admin/become", status_code=303)
        return await func(request)

    return wrapper


# ===========================================================================
#  Кошик (зберігається у cookie-сесії)
#  Формат: list[ item ], де item = {
#     "product_id": int,
#     "quantity": int,
#     "selections": [ {"value_id": int, "text": str|None}, ... ]
#  }
# ===========================================================================
def get_cart(request: Request) -> list[dict]:
    return request.session.get("cart", [])


def save_cart(request: Request, cart: list[dict]) -> None:
    request.session["cart"] = cart


def add_to_cart(request: Request, product_id: int, selections: list[dict], quantity: int = 1) -> None:
    cart = get_cart(request)
    cart.append({"product_id": product_id, "quantity": max(1, quantity), "selections": selections})
    save_cart(request, cart)


def remove_from_cart(request: Request, index: int) -> None:
    cart = get_cart(request)
    if 0 <= index < len(cart):
        cart.pop(index)
    save_cart(request, cart)


def clear_cart(request: Request) -> None:
    request.session.pop("cart", None)


# ===========================================================================
#  Розрахунок ціни — ЄДИНЕ ДЖЕРЕЛО ПРАВДИ (рахуємо з БД, не з cookie!)
# ===========================================================================
def product_discount_valid(d: ProductDiscount) -> bool:
    """Знижка на товар діє: активна, в межах дат, ліміт замовлень не вичерпано."""
    if not d.is_active:
        return False
    now = datetime.utcnow()
    start = _as_naive_utc(d.starts_at)
    if start is not None and start > now:
        return False
    exp = _as_naive_utc(d.expires_at)
    if exp is not None and exp <= now:
        return False
    if d.max_orders and d.orders_used >= d.max_orders:
        return False
    return True


def _apply_product_discount(d: ProductDiscount, base: decimal.Decimal, mods_total: decimal.Decimal):
    """Повертає (знижена_unit, сума_знижки) для однієї знижки на товар.

    scope='base' — знижка лише на базову ціну; 'full' — на (база + модифікації).
    """
    unit = money(base + mods_total)
    target = base if d.scope == DISCOUNT_SCOPE_BASE else unit
    if d.kind == DISCOUNT_PERCENT:
        red = money(money(target) * money(d.value) / 100)
    else:
        red = money(d.value)
    red = _clamp(red, money(target))  # не більше за ту частину, на яку діє
    return money(unit - red), red


def best_product_discount(product: Product, base: decimal.Decimal, mods_total: decimal.Decimal):
    """Найвигідніша діюча знижка на товар. Повертає (ProductDiscount|None, знижена_unit).

    Кілька знижок на товар => береться та, що дає найбільше зменшення;
    нічия => найменший id (детермінованість).
    """
    unit = money(base + mods_total)
    candidates = [d for d in product.discounts if product_discount_valid(d)]
    if not candidates:
        return None, unit
    scored = []
    for d in candidates:
        cand_unit, red = _apply_product_discount(d, base, mods_total)
        scored.append((red, -d.id, d, cand_unit))
    scored.sort(reverse=True)  # макс. знижка, потім max(-id) => min id
    red, _neg_id, d, cand_unit = scored[0]
    if red <= ZERO:
        return None, unit
    return d, cand_unit


def effective_stickers(product: Product) -> list:
    """Стікери товару: призначені вручну + від активних знижок на цей товар.

    Стікер знижки показується лише поки знижка діє (період/ліміт/активність).
    Дедуплікація за id; ручні стікери першими.
    """
    result = list(product.stickers)
    seen = {s.id for s in result}
    for d in product.discounts:
        if d.sticker is not None and product_discount_valid(d) and d.sticker.id not in seen:
            result.append(d.sticker)
            seen.add(d.sticker.id)
    return result


def price_cart_item(db: Session, item: dict) -> dict | None:
    """Розкриває один елемент кошика в детальну позицію з цінами з БД.

    Повертає None, якщо товар більше не існує/неактивний.
    Ціна = base_price + Σ(ціна вибраних значень) - знижка на товар (якщо діє).
    """
    product = db.get(Product, item["product_id"])
    if product is None or not product.is_active:
        return None

    qty = max(1, int(item.get("quantity", 1)))
    base = money(product.base_price)
    mods_total = ZERO
    mods = []
    for sel in item.get("selections", []):
        value = db.get(ModificationValue, sel.get("value_id"))
        if value is None:
            continue
        mods_total += money(value.price)
        mods.append(
            {
                "value": value,
                "label": f"{value.modification.name}: {value.label}",
                "price": money(value.price),
                "text": (sel.get("text") or None) if value.is_custom_text else None,
            }
        )
    orig_unit = money(base + mods_total)
    pd, eff_unit = best_product_discount(product, base, mods_total)
    eff_unit = money(eff_unit)
    return {
        "product": product,
        "quantity": qty,
        "base_price": base,
        "orig_unit_price": orig_unit,  # до знижки на товар
        "unit_price": eff_unit,  # після знижки на товар
        "orig_line_total": money(orig_unit * qty),
        "line_total": money(eff_unit * qty),
        "product_discount": pd,
        "product_discount_amount": money((orig_unit - eff_unit) * qty),
        "mods": mods,
    }


def price_cart(db: Session, cart: list[dict]) -> tuple[list[dict], decimal.Decimal, decimal.Decimal]:
    """Повертає (детальні позиції, subtotal_orig, subtotal_pd).

    subtotal_orig — сума до знижок на товар (headline);
    subtotal_pd — сума після знижок на товар (база для акаунтної/код-знижки).
    Пропускає мертві товари.
    """
    detailed = []
    subtotal_orig = ZERO
    subtotal_pd = ZERO
    for item in cart:
        priced = price_cart_item(db, item)
        if priced is None:
            continue
        detailed.append(priced)
        subtotal_orig += priced["orig_line_total"]
        subtotal_pd += priced["line_total"]
    return detailed, money(subtotal_orig), money(subtotal_pd)


# ===========================================================================
#  Знижки (акаунтна % та коди)
# ===========================================================================
def _clamp(amount: decimal.Decimal, subtotal: decimal.Decimal) -> decimal.Decimal:
    """Знижка не може бути < 0 і не більша за суму (=> total >= 0)."""
    if amount < ZERO:
        return ZERO
    if amount > subtotal:
        return subtotal
    return money(amount)


def _fmt_pct(value: decimal.Decimal) -> str:
    v = decimal.Decimal(value)
    return f"{v.normalize():f}" if v == v.to_integral() else f"{v:.2f}"


def _as_naive_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def code_is_valid(code: DiscountCode) -> tuple[bool, str]:
    """Перевірка коду: активність, термін дії, ліміт активацій."""
    if not code.is_active:
        return False, "Код неактивний."
    exp = _as_naive_utc(code.expires_at)
    if exp is not None and exp <= datetime.utcnow():
        return False, "Термін дії коду завершився."
    if code.max_activations and code.activations_used >= code.max_activations:
        return False, "Вичерпано ліміт активацій коду."
    return True, ""


def _eligible_subtotal(detailed: list[dict], stack_attr: str) -> decimal.Decimal:
    """Сума позицій (після знижки на товар), на які можна накласти знижку типу stack_attr.

    Позиція придатна, якщо на ній немає знижки на товар АБО та знижка
    дозволяє сумування (stack_account / stack_code).
    """
    total = ZERO
    for d in detailed:
        pd = d.get("product_discount")
        if pd is None or getattr(pd, stack_attr):
            total += d["line_total"]
    return money(total)


def compute_discount(db: Session, user: User, detailed: list[dict], code_str: str = "") -> dict:
    """Рахує замовну знижку (акаунтну % або код) поверх знижок на товар.

    ЄДИНЕ ДЖЕРЕЛО ПРАВДИ. `detailed` — позиції з price_cart (з line_total
    після знижки на товар і прапорцем product_discount на кожній).

    Правила:
      - Акаунтна знижка (%) має пріоритет і блокує коди.
      - Код діє лише якщо на акаунті немає знижки.
      - Накладається лише на придатні позиції (eligible-portion) за прапорцями
        stack_account / stack_code знижки на товар.
      - Фіксована сума більша за придатну суму => знижка = придатна сума.
    Повертає: {amount, source, label, code, error}.
    """
    code_str = (code_str or "").strip()
    subtotal_pd = money(sum((d["line_total"] for d in detailed), ZERO))
    acc_pct = money(user.discount_percent or ZERO)

    if acc_pct > 0:
        eligible = _eligible_subtotal(detailed, "stack_account")
        amount = _clamp(money(eligible * acc_pct / 100), subtotal_pd)
        error = "Код не застосовано: на акаунті діє постійна знижка." if code_str else None
        return {
            "amount": amount,
            "source": "account",
            "label": f"Акаунтна знижка −{_fmt_pct(acc_pct)}%",
            "code": None,
            "error": error,
        }

    if not code_str:
        return {"amount": ZERO, "source": "", "label": "", "code": None, "error": None}

    code = db.query(DiscountCode).filter_by(code=code_str).first()
    if code is None:
        return {"amount": ZERO, "source": "", "label": "", "code": None, "error": "Код не знайдено."}
    ok, msg = code_is_valid(code)
    if not ok:
        return {"amount": ZERO, "source": "", "label": "", "code": None, "error": msg}

    eligible = _eligible_subtotal(detailed, "stack_code")
    if code.kind == DISCOUNT_PERCENT:
        amount = _clamp(money(eligible * money(code.value) / 100), subtotal_pd)
        label = f"Код {code.code} (−{_fmt_pct(code.value)}%)"
    else:  # DISCOUNT_AMOUNT
        amount = _clamp(money(code.value), eligible)
        label = f"Код {code.code} (−{money(code.value)} грн)"
    return {"amount": amount, "source": "code", "label": label, "code": code, "error": None}


# ===========================================================================
#  Створення замовлення з кошика (статус "нове")
# ===========================================================================
def _next_order_number(db: Session) -> int:
    """Наступний видимий номер замовлення (з урахуванням стартового номера)."""
    from app.np_settings import get_settings

    start = get_settings(db).order_start_number or 1
    last = db.query(func.max(Order.number)).scalar() or 0
    return max(start, last + 1)


def create_order(
    db: Session,
    user: User,
    cart: list[dict],
    shipping: dict,
    code_str: str = "",
) -> Order:
    """Створює замовлення. `shipping` містить дані доставки Нова Пошта:
    full_name, recipient_phone, city, np_city_ref, np_city_name,
    np_warehouse_ref, np_warehouse_name, np_warehouse_type.
    """
    detailed, subtotal_orig, subtotal_pd = price_cart(db, cart)
    if not detailed:
        raise ValueError("Кошик порожній")

    product_discount_amount = money(subtotal_orig - subtotal_pd)
    disc = compute_discount(db, user, detailed, code_str)
    discount_amount = disc["amount"]
    total = money(subtotal_pd - discount_amount)

    status_new = _status_by_role(db, ROLE_NEW, STATUS_NEW)
    order = Order(
        number=_next_order_number(db),
        user_id=user.id,
        status_id=status_new.id,
        full_name=shipping.get("full_name", ""),
        recipient_phone=shipping.get("recipient_phone", ""),
        city=shipping.get("np_city_name") or shipping.get("city", ""),
        np_city_ref=shipping.get("np_city_ref", ""),
        np_city_name=shipping.get("np_city_name", ""),
        np_branch=shipping.get("np_warehouse_name", ""),
        np_warehouse_ref=shipping.get("np_warehouse_ref", ""),
        np_warehouse_type=shipping.get("np_warehouse_type", ""),
        subtotal=subtotal_orig,
        product_discount_amount=product_discount_amount,
        discount_amount=discount_amount,
        discount_source=disc["source"],
        discount_label=disc["label"],
        discount_code_id=disc["code"].id if disc["code"] else None,
        total_price=total,
    )
    db.add(order)
    db.flush()

    # Початковий запис журналу статусів (створення => "нове").
    db.add(OrderStatusLog(order_id=order.id, from_status=None, to_status=status_new.name))

    # Лог активації коду + інкремент лічильника.
    if disc["source"] == "code" and disc["code"] is not None:
        code = disc["code"]
        code.activations_used = (code.activations_used or 0) + 1
        db.add(
            DiscountActivation(
                code_id=code.id,
                user_id=user.id,
                order_id=order.id,
                discount_amount=discount_amount,
            )
        )

    # Інкремент лічильника замовлень для застосованих знижок на товар
    # (кожна унікальна знижка рахується раз на замовлення; вичерпання => вимикається).
    applied_pd_ids = {d["product_discount"].id for d in detailed if d.get("product_discount") is not None}
    for pd_id in applied_pd_ids:
        pd = db.get(ProductDiscount, pd_id)
        if pd is not None:
            pd.orders_used = (pd.orders_used or 0) + 1
            if pd.max_orders and pd.orders_used >= pd.max_orders:
                pd.is_active = False

    for d in detailed:
        oi = OrderItem(
            order_id=order.id,
            product_id=d["product"].id,
            product_name=d["product"].name,
            base_price=d["base_price"],
            quantity=d["quantity"],
            line_total=d["line_total"],
        )
        db.add(oi)
        db.flush()
        for m in d["mods"]:
            db.add(
                OrderItemModification(
                    order_item_id=oi.id,
                    modification_value_id=m["value"].id,
                    label=m["label"],
                    custom_text=m["text"],
                    price=m["price"],
                )
            )
    return order


def build_waybill_description(order: Order, limit: int = 250) -> str:
    """Опис для ЕН: номер замовлення + товари з опціями.

    Без символів, які відхиляє Нова Пошта (×, двокрапки тощо).
    """
    parts = []
    for it in order.items:
        s = it.product_name
        if it.quantity and it.quantity > 1:
            s += f" x{it.quantity}"
        mods = []
        for m in it.modifications:
            label = m.label.replace(":", " -")
            if m.custom_text:
                label += f" - {m.custom_text}"
            mods.append(label)
        if mods:
            s += " (" + ", ".join(mods) + ")"
        parts.append(s)
    desc = f"Замовлення N{order.number or order.id}. " + ", ".join(parts)
    return desc[:limit]


# ===========================================================================
#  State-machine flow статусів
# ===========================================================================
def available_transitions(db: Session, order: Order) -> list[OrderStatus]:
    """Статуси, у які можна перевести замовлення з поточного.

    Будь-який статус → будь-який інший (окрім самого себе). Термінальних
    статусів немає — з "завершене"/"скасоване" теж можна перейти далі.
    """
    return db.query(OrderStatus).filter(OrderStatus.id != order.status_id).order_by(OrderStatus.position).all()


def _status_by_role(db: Session, role: str, fallback_name: str) -> OrderStatus | None:
    """Фіксований статус за роллю (стабільно), із запасним пошуком за назвою."""
    s = db.query(OrderStatus).filter_by(role=role).first()
    if s is None:
        s = db.query(OrderStatus).filter_by(name=fallback_name).first()
    return s


def move_order(db: Session, order: Order, target_status_id: int) -> bool:
    """Переводить замовлення в target_status_id, якщо це дозволено. Логує перехід."""
    allowed = {s.id for s in available_transitions(db, order)}
    if target_status_id not in allowed:
        return False
    from_name = order.status.name
    target = db.get(OrderStatus, target_status_id)
    order.status_id = target_status_id
    db.add(OrderStatusLog(order_id=order.id, from_status=from_name, to_status=target.name))
    return True


def cancel_order(db: Session, order: Order) -> bool:
    cancelled = _status_by_role(db, ROLE_CANCELLED, STATUS_CANCELLED)
    return move_order(db, order, cancelled.id)


# ===========================================================================
#  Адмін-ключі
# ===========================================================================
def generate_admin_key(db: Session, created_by: User) -> str:
    from app.models import AdminKey

    key = secrets.token_urlsafe(24)
    db.add(AdminKey(key=key, created_by_id=created_by.id))
    return key


def generate_discount_code(length: int = 8) -> str:
    """Випадковий код знижки (великі літери + цифри, без неоднозначних)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))
