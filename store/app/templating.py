"""Jinja2 + хелпер рендеру, що інжектить спільний контекст у кожну сторінку."""

import decimal

import markdown as md
from markupsafe import Markup
from starlette.requests import Request
from starlette.templating import Jinja2Templates

from app.config import BASE_DIR, MEDIA_URL
from app.core import best_product_discount, current_user, effective_stickers, get_cart, pop_flashes

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _format_price(value) -> str:
    if value is None:
        return "0.00"
    return f"{decimal.Decimal(value):.2f}"


def _discounted(value, pct) -> str:
    """Ціна з урахуванням акаунтної знижки (%)."""
    if value is None:
        return "0.00"
    v = decimal.Decimal(value)
    p = decimal.Decimal(pct or 0)
    final = (v * (decimal.Decimal(100) - p) / decimal.Decimal(100)).quantize(decimal.Decimal("0.01"))
    if final < 0:
        final = decimal.Decimal("0.00")
    return f"{final:.2f}"


def _markdown(text) -> Markup:
    """Markdown -> HTML (контент від адміна, тому довіряємо)."""
    if not text:
        return Markup("")
    return Markup(md.markdown(text, extensions=["extra", "sane_lists", "nl2br"]))


def _card_price(product, account_pct) -> dict:
    """Ціна «від» для картки: базова з урахуванням знижки на товар + акаунтної.

    Повертає {orig, final, discounted}. Якщо на товарі діє знижка, що не
    сумується з акаунтною — акаунтна на цю частину не накладається.
    """
    base = decimal.Decimal(product.base_price)
    zero = decimal.Decimal("0.00")
    pd, unit = best_product_discount(product, base, zero)
    final = decimal.Decimal(unit)
    acc = decimal.Decimal(account_pct or 0)
    if (pd is None or pd.stack_account) and acc > 0:
        final = final * (decimal.Decimal(100) - acc) / decimal.Decimal(100)
    final = final.quantize(decimal.Decimal("0.01"))
    if final < 0:
        final = zero
    return {
        "orig": base.quantize(decimal.Decimal("0.01")),
        "final": final,
        "discounted": final < base,
    }


templates.env.filters["price"] = _format_price
templates.env.filters["discounted"] = _discounted
templates.env.filters["markdown"] = _markdown
templates.env.filters["card_price"] = _card_price
templates.env.filters["stickers"] = effective_stickers


def render(request: Request, template: str, context: dict | None = None, **kwargs):
    """Рендер шаблону зі спільним контекстом (user, flashes, кошик).

    Передавайте `db` у context, якщо потрібен поточний user у шаблоні.
    """
    ctx = dict(context or {})
    ctx.update(kwargs)
    db = ctx.pop("db", None)
    user = current_user(request, db) if db is not None else None
    ctx["request"] = request
    ctx["current_user"] = user
    # Акаунтна знижка (%) для показу фінальних цін у каталозі.
    ctx["account_discount_pct"] = (
        decimal.Decimal(user.discount_percent) if user and user.discount_percent else decimal.Decimal(0)
    )
    ctx["flashes"] = pop_flashes(request)
    ctx["cart_count"] = len(get_cart(request))
    ctx["media_url"] = MEDIA_URL
    status = ctx.pop("status_code", 200)
    return templates.TemplateResponse(request, template, ctx, status_code=status)
