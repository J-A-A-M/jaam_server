"""Юзер-частина: каталог, товар, кошик, оформлення, реєстрація, кабінет."""

from urllib.parse import urlparse

from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from app import nova_poshta
from app.core import (
    add_to_cart,
    best_product_discount,
    clear_cart,
    compute_discount,
    create_order,
    current_user,
    flash,
    get_cart,
    login_user,
    logout_user,
    money,
    price_cart,
    remove_from_cart,
)
from app.db import get_db
from app.models import Category, ModificationValue, Order, Product, User
from app.security import hash_password, verify_password
from app.templating import render


# --- Головна / каталог ------------------------------------------------------
async def home(request):
    with get_db() as db:
        # На головній — лише товари з show_on_home, відсортовані за позицією.
        products = (
            db.query(Product)
            .filter_by(is_active=True, show_on_home=True)
            .order_by(Product.position, Product.name)
            .all()
        )
        roots = db.query(Category).filter_by(parent_id=None).order_by(Category.name).all()
        return render(
            request,
            "storefront/home.html",
            {"db": db, "products": products, "categories": roots},
        )


async def category_view(request):
    cid = int(request.path_params["id"])
    with get_db() as db:
        category = db.get(Category, cid)
        if category is None:
            flash(request, "Розділ не знайдено.", "warning")
            return RedirectResponse("/", status_code=303)
        # Товари розділу, відсортовані за позицією.
        products = sorted(
            [p for p in category.products if p.is_active],
            key=lambda p: (p.position, p.name),
        )
        return render(
            request,
            "storefront/category.html",
            {"db": db, "category": category, "products": products},
        )


async def product_view(request):
    pid = int(request.path_params["id"])
    with get_db() as db:
        product = db.get(Product, pid)
        if product is None or not product.is_active:
            flash(request, "Товар не знайдено.", "warning")
            return RedirectResponse("/", status_code=303)
        # Активна знижка на товар (для показу та JS-перерахунку ціни).
        pd, _unit = best_product_discount(product, money(product.base_price), money(0))
        return render(
            request,
            "storefront/product.html",
            {"db": db, "product": product, "product_discount": pd},
        )


# --- Кошик ------------------------------------------------------------------
async def cart_add(request):
    form = await request.form()
    pid = int(form["product_id"])
    quantity = int(form.get("quantity", 1) or 1)

    with get_db() as db:
        product = db.get(Product, pid)
        if product is None or not product.is_active:
            flash(request, "Товар не знайдено.", "warning")
            return RedirectResponse("/", status_code=303)

        selections = []
        # Для кожної модифікації товару очікуємо mod_<modification_id>=<value_id>
        for mod in product.modifications:
            raw = form.get(f"mod_{mod.id}")
            if not raw:
                continue
            value_id = int(raw)
            value = db.get(ModificationValue, value_id)
            if value is None or value.modification_id != mod.id:
                continue
            sel = {"value_id": value_id, "text": None}
            if value.is_custom_text:
                sel["text"] = (form.get(f"text_{mod.id}") or "").strip() or None
            selections.append(sel)

    add_to_cart(request, pid, selections, quantity)
    flash(request, "Товар додано до кошика.", "success")
    return RedirectResponse("/cart", status_code=303)


async def cart_view(request):
    with get_db() as db:
        items, subtotal_orig, total = price_cart(db, get_cart(request))
        return render(
            request,
            "storefront/cart.html",
            {
                "db": db,
                "items": items,
                "subtotal_orig": subtotal_orig,
                "product_discount": money(subtotal_orig - total),
                "total": total,
            },
        )


async def cart_remove(request):
    form = await request.form()
    remove_from_cart(request, int(form["index"]))
    flash(request, "Позицію видалено.", "info")
    return RedirectResponse("/cart", status_code=303)


# --- Оформлення -------------------------------------------------------------
async def checkout(request):
    with get_db() as db:
        user = current_user(request, db)
        if user is None:
            flash(request, "Щоб оформити замовлення, увійдіть у систему.", "warning")
            return RedirectResponse("/login?next=/checkout", status_code=303)

        cart = get_cart(request)
        items, subtotal_orig, total = price_cart(db, cart)
        if not items:
            flash(request, "Кошик порожній.", "warning")
            return RedirectResponse("/cart", status_code=303)

        code_str = ""
        if request.method == "POST":
            form = await request.form()
            shipping = {
                "full_name": (form.get("full_name") or "").strip(),
                "recipient_phone": (form.get("recipient_phone") or "").strip(),
                "np_city_ref": (form.get("np_city_ref") or "").strip(),
                "np_city_name": (form.get("np_city_name") or "").strip(),
                "np_warehouse_ref": (form.get("np_warehouse_ref") or "").strip(),
                "np_warehouse_name": (form.get("np_warehouse_name") or "").strip(),
                "np_warehouse_type": (form.get("np_warehouse_type") or "").strip(),
            }
            code_str = (form.get("discount_code") or "").strip()

            disc = compute_discount(db, user, items, code_str)
            required = (
                shipping["full_name"]
                and shipping["recipient_phone"]
                and shipping["np_city_ref"]
                and shipping["np_warehouse_ref"]
            )
            # Якщо введено код, але він невалідний — не оформлюємо, даємо виправити.
            if code_str and disc["source"] != "code":
                flash(request, disc["error"] or "Код знижки недійсний.", "danger")
            elif not required:
                flash(request, "Заповніть ПІБ, телефон, місто та відділення/поштомат.", "danger")
            else:
                order = create_order(db, user, cart, shipping, code_str)
                db.flush()
                order_id = order.id
                order_number = order.number
                # Запамʼятати профіль для наступних замовлень.
                if not user.full_name:
                    user.full_name = shipping["full_name"]
                if not user.phone:
                    user.phone = shipping["recipient_phone"]
                clear_cart(request)
                flash(request, f"Замовлення №{order_number} створено (статус «нове»).", "success")
                return RedirectResponse(f"/account/orders/{order_id}", status_code=303)

        # Попередній розрахунок знижки для початкового рендеру.
        disc = compute_discount(db, user, items, code_str)
        return render(
            request,
            "storefront/checkout.html",
            {
                "db": db,
                "items": items,
                "subtotal_orig": subtotal_orig,
                "product_discount": money(subtotal_orig - total),
                "total": total,
                "user": user,
                "account_discount": money(user.discount_percent or 0),
                "discount": disc,
                "code_str": code_str,
                "final_total": money(total - disc["amount"]),
            },
        )


# --- Nova Poshta proxy (для автодоповнення на checkout) ---------------------
async def np_cities(request):
    user_id = request.session.get("user_id")
    if user_id is None:
        return JSONResponse({"error": "Не авторизовано"}, status_code=401)
    query = (request.query_params.get("q") or "").strip()
    try:
        cities = await nova_poshta.search_cities(query)
    except nova_poshta.NovaPoshtaError as e:
        return JSONResponse({"error": str(e), "items": []})
    return JSONResponse({"items": cities})


async def np_warehouses(request):
    user_id = request.session.get("user_id")
    if user_id is None:
        return JSONResponse({"error": "Не авторизовано"}, status_code=401)
    city_ref = (request.query_params.get("city_ref") or "").strip()
    query = (request.query_params.get("q") or "").strip()
    category = "postomat" if (request.query_params.get("type") == "postomat") else ""
    try:
        result = await nova_poshta.get_warehouses(city_ref, query, category)
    except nova_poshta.NovaPoshtaError as e:
        return JSONResponse({"error": str(e), "branches": [], "postomats": []})
    return JSONResponse(result)


async def checkout_preview(request):
    """JSON-перерахунок знижки за кодом (для динамічного показу на checkout)."""
    with get_db() as db:
        user = current_user(request, db)
        if user is None:
            return JSONResponse({"error": "Не авторизовано"}, status_code=401)
        cart = get_cart(request)
        detailed, _subtotal_orig, subtotal = price_cart(db, cart)
        form = await request.form()
        code_str = (form.get("discount_code") or "").strip()
        disc = compute_discount(db, user, detailed, code_str)
        final_total = money(subtotal - disc["amount"])
        return JSONResponse(
            {
                "subtotal": f"{subtotal:.2f}",
                "discount": f"{disc['amount']:.2f}",
                "label": disc["label"],
                "source": disc["source"],
                "total": f"{final_total:.2f}",
                "error": disc["error"],
            }
        )


# --- Реєстрація / вхід ------------------------------------------------------
async def register(request):
    if request.method == "POST":
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""
        with get_db() as db:
            if not email or not password:
                flash(request, "Email і пароль обовʼязкові.", "danger")
            elif db.query(User).filter_by(email=email).first():
                flash(request, "Такий email вже зареєстровано.", "danger")
            else:
                user = User(email=email, password_hash=hash_password(password))
                db.add(user)
                db.flush()
                login_user(request, user)  # одразу логінимо
                flash(request, "Реєстрація успішна. Вітаємо!", "success")
                return RedirectResponse("/", status_code=303)
    return render(request, "storefront/register.html", {})


def _safe_next(url: str) -> str:
    """Дозволяє лише локальні відносні шляхи — захист від open redirect."""
    if not url or not url.startswith("/") or url.startswith("//"):
        return "/"
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        return "/"
    return url


async def login(request):
    next_url = _safe_next(request.query_params.get("next", "/"))
    if request.method == "POST":
        form = await request.form()
        email = (form.get("email") or "").strip().lower()
        password = form.get("password") or ""
        next_url = _safe_next(form.get("next", "/"))
        with get_db() as db:
            user = db.query(User).filter_by(email=email).first()
            if user and verify_password(password, user.password_hash):
                login_user(request, user)
                flash(request, "Ви увійшли.", "success")
                return RedirectResponse(next_url, status_code=303)
            flash(request, "Невірний email або пароль.", "danger")
    return render(request, "storefront/login.html", {"next_url": next_url})


async def logout(request):
    logout_user(request)
    flash(request, "Ви вийшли.", "info")
    return RedirectResponse("/", status_code=303)


# --- Кабінет ----------------------------------------------------------------
async def account(request):
    with get_db() as db:
        user = current_user(request, db)
        if user is None:
            return RedirectResponse("/login?next=/account", status_code=303)
        orders = db.query(Order).filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
        return render(request, "storefront/account.html", {"db": db, "orders": orders})


async def account_order(request):
    oid = int(request.path_params["id"])
    with get_db() as db:
        user = current_user(request, db)
        if user is None:
            return RedirectResponse("/login", status_code=303)
        order = db.get(Order, oid)
        if order is None or order.user_id != user.id:
            flash(request, "Замовлення не знайдено.", "warning")
            return RedirectResponse("/account", status_code=303)
        return render(request, "storefront/order.html", {"db": db, "order": order})


async def account_profile(request):
    """Редагування профілю доставки (ПІБ, телефон) — потрібно для ЕН."""
    with get_db() as db:
        user = current_user(request, db)
        if user is None:
            return RedirectResponse("/login?next=/account/profile", status_code=303)
        if request.method == "POST":
            form = await request.form()
            user.full_name = (form.get("full_name") or "").strip()
            user.phone = (form.get("phone") or "").strip()
            flash(request, "Профіль збережено.", "success")
            return RedirectResponse("/account", status_code=303)
        return render(request, "storefront/profile.html", {"db": db, "user": user})


routes = [
    Route("/", home),
    Route("/category/{id:int}", category_view),
    Route("/product/{id:int}", product_view),
    Route("/cart", cart_view),
    Route("/cart/add", cart_add, methods=["POST"]),
    Route("/cart/remove", cart_remove, methods=["POST"]),
    Route("/checkout", checkout, methods=["GET", "POST"]),
    Route("/checkout/preview", checkout_preview, methods=["POST"]),
    Route("/np/cities", np_cities),
    Route("/np/warehouses", np_warehouses),
    Route("/register", register, methods=["GET", "POST"]),
    Route("/login", login, methods=["GET", "POST"]),
    Route("/logout", logout),
    Route("/account", account),
    Route("/account/profile", account_profile, methods=["GET", "POST"]),
    Route("/account/orders/{id:int}", account_order),
]
