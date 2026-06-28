"""ORM-моделі магазину (SQLAlchemy 2.x).

Заміна SQL-бази робиться через DATABASE_URL — моделі не залежать від діалекту.
Грошові поля — Numeric(10,2) (Decimal), щоб уникнути float-похибок.
"""

from __future__ import annotations

import decimal
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

ZERO = decimal.Decimal("0.00")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --- Асоціативні таблиці many-to-many --------------------------------------
product_category = Table(
    "product_category",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("categories.id", ondelete="CASCADE"), primary_key=True),
)

product_modification = Table(
    "product_modification",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("modification_id", ForeignKey("modifications.id", ondelete="CASCADE"), primary_key=True),
)

product_sticker = Table(
    "product_sticker",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("sticker_id", ForeignKey("stickers.id", ondelete="CASCADE"), primary_key=True),
)

product_discount_product = Table(
    "product_discount_product",
    Base.metadata,
    Column("product_id", ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column("discount_id", ForeignKey("product_discounts.id", ondelete="CASCADE"), primary_key=True),
)


# --- Користувачі та адміни --------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    # Постійна знижка акаунта у відсотках (0..100). >0 => коди знижок не діють.
    discount_percent: Mapped[decimal.Decimal] = mapped_column(Numeric(5, 2), default=ZERO)
    # Профіль для доставки (потрібно для ЕН Нова Пошта).
    full_name: Mapped[str] = mapped_column(String(255), default="")
    phone: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class AdminKey(Base):
    """Згенерований ключ для створення адміна (одноразовий)."""

    __tablename__ = "admin_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    used_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    used_by: Mapped["User | None"] = relationship(foreign_keys=[used_by_id])


# --- Коди знижок ------------------------------------------------------------
DISCOUNT_PERCENT = "percent"
DISCOUNT_AMOUNT = "amount"

# Область дії знижки на товар: лише базова ціна або вся (з модифікаціями).
DISCOUNT_SCOPE_BASE = "base"
DISCOUNT_SCOPE_FULL = "full"


class DiscountCode(Base):
    """Код знижки. kind: 'percent' (value = %) або 'amount' (value = грн).

    max_activations=0 => без обмеження. expires_at=None => безстроково.
    """

    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16), default=DISCOUNT_PERCENT)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    max_activations: Mapped[int] = mapped_column(Integer, default=0)
    activations_used: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    activations: Mapped[list["DiscountActivation"]] = relationship(
        back_populates="code",
        cascade="all, delete-orphan",
        order_by="DiscountActivation.created_at.desc()",
    )


class DiscountActivation(Base):
    """Лог застосування коду знижки до замовлення."""

    __tablename__ = "discount_activations"

    id: Mapped[int] = mapped_column(primary_key=True)
    code_id: Mapped[int] = mapped_column(ForeignKey("discount_codes.id", ondelete="CASCADE"))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))
    discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    code: Mapped["DiscountCode"] = relationship(back_populates="activations")
    user: Mapped["User | None"] = relationship()


# --- Каталог ----------------------------------------------------------------
class Category(Base):
    """Розділ товарів. Може вкладатися сам у себе (parent_id)."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id", ondelete="CASCADE"))

    parent: Mapped["Category | None"] = relationship(back_populates="children", remote_side=[id])
    children: Mapped[list["Category"]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    products: Mapped[list["Product"]] = relationship(secondary=product_category, back_populates="categories")


class Modification(Base):
    """Параметр товару (напр. "Колір"), що приймає одне зі значень."""

    __tablename__ = "modifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))

    values: Mapped[list["ModificationValue"]] = relationship(
        back_populates="modification",
        cascade="all, delete-orphan",
        order_by="ModificationValue.position",
    )
    products: Mapped[list["Product"]] = relationship(secondary=product_modification, back_populates="modifications")


class ModificationValue(Base):
    """Конкретне значення модифікації зі своєю ціною (може бути 0).

    is_custom_text=True — юзер сам вводить опис для замовлення.
    """

    __tablename__ = "modification_values"

    id: Mapped[int] = mapped_column(primary_key=True)
    modification_id: Mapped[int] = mapped_column(ForeignKey("modifications.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(255))
    price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    is_custom_text: Mapped[bool] = mapped_column(Boolean, default=False)
    # Вимкнений варіант не показується покупцю, але не видаляється.
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    modification: Mapped["Modification"] = relationship(back_populates="values")


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")  # короткий опис (картки)
    long_description: Mapped[str] = mapped_column(Text, default="")  # markdown для сторінки товару
    base_price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # порядок сортування
    show_on_home: Mapped[bool] = mapped_column(Boolean, default=False)  # показувати на головній

    categories: Mapped[list["Category"]] = relationship(secondary=product_category, back_populates="products")
    modifications: Mapped[list["Modification"]] = relationship(
        secondary=product_modification, back_populates="products"
    )
    images: Mapped[list["ProductImage"]] = relationship(
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.position",
    )
    stickers: Mapped[list["Sticker"]] = relationship(secondary=product_sticker, back_populates="products")
    discounts: Mapped[list["ProductDiscount"]] = relationship(
        secondary=product_discount_product, back_populates="products"
    )


class ProductImage(Base):
    """Фотографія товару. Кілька фото на товар => карусель у картці."""

    __tablename__ = "product_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    filename: Mapped[str] = mapped_column(String(255))  # імʼя файла в UPLOAD_DIR
    position: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped["Product"] = relationship(back_populates="images")


class Sticker(Base):
    """Стікер-мітка на товар ("Розпродаж", "Хіт" тощо)."""

    __tablename__ = "stickers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64))
    color: Mapped[str] = mapped_column(String(16), default="#dc3545")  # фон бейджа
    text_color: Mapped[str] = mapped_column(String(16), default="#ffffff")

    products: Mapped[list["Product"]] = relationship(secondary=product_sticker, back_populates="stickers")


class ProductDiscount(Base):
    """Знижка на товар. Призначається товарам (M2M).

    kind: 'percent' (value=%) або 'amount' (value=грн).
    scope: 'base' (лише базова ціна) або 'full' (база + модифікації).
    max_orders=0 => без обмеження; expires_at=None => безстроково.
    stack_account/stack_code => чи сумується з акаунтною знижкою/промокодом.
    """

    __tablename__ = "product_discounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16), default=DISCOUNT_PERCENT)
    value: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    scope: Mapped[str] = mapped_column(String(16), default=DISCOUNT_SCOPE_FULL)
    max_orders: Mapped[int] = mapped_column(Integer, default=0)
    orders_used: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime)  # None => діє відразу
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    stack_account: Mapped[bool] = mapped_column(Boolean, default=False)
    stack_code: Mapped[bool] = mapped_column(Boolean, default=False)
    # Стікер, що активується на товарах знижки на період її дії (опціонально).
    sticker_id: Mapped[int | None] = mapped_column(ForeignKey("stickers.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    products: Mapped[list["Product"]] = relationship(secondary=product_discount_product, back_populates="discounts")
    sticker: Mapped["Sticker | None"] = relationship()


# --- Статуси замовлень та flow ---------------------------------------------
class OrderStatus(Base):
    """Статус замовлення. Фіксовані (is_fixed): нове, завершене, скасоване."""

    __tablename__ = "order_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Стабільна роль фіксованого статусу (''|'new'|'done'|'cancelled'),
    # щоб код не залежав від назви (її можна перейменувати).
    role: Mapped[str] = mapped_column(String(16), default="")
    color: Mapped[str] = mapped_column(String(16), default="#007bff")  # фон бейджа
    text_color: Mapped[str] = mapped_column(String(16), default="#ffffff")
    position: Mapped[int] = mapped_column(Integer, default=0)


class StatusTransition(Base):
    """Дозволений перехід у загальному flow (from -> to)."""

    __tablename__ = "status_transitions"
    __table_args__ = (UniqueConstraint("from_status_id", "to_status_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    from_status_id: Mapped[int] = mapped_column(ForeignKey("order_statuses.id", ondelete="CASCADE"))
    to_status_id: Mapped[int] = mapped_column(ForeignKey("order_statuses.id", ondelete="CASCADE"))

    from_status: Mapped["OrderStatus"] = relationship(foreign_keys=[from_status_id])
    to_status: Mapped["OrderStatus"] = relationship(foreign_keys=[to_status_id])


# --- Замовлення -------------------------------------------------------------
# Поля товару/ціни знімаються "знімком" у момент замовлення, щоб подальше
# редагування каталогу не міняло історичні замовлення.
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, default=0, index=True)  # видимий № замовлення
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status_id: Mapped[int] = mapped_column(ForeignKey("order_statuses.id"))
    full_name: Mapped[str] = mapped_column(String(255))
    recipient_phone: Mapped[str] = mapped_column(String(32), default="")
    city: Mapped[str] = mapped_column(String(255))
    # Дані Нова Пошта для відправлення.
    np_city_ref: Mapped[str] = mapped_column(String(64), default="")
    np_city_name: Mapped[str] = mapped_column(String(255), default="")
    np_branch: Mapped[str] = mapped_column(String(255))  # назва відділення/поштомата
    np_warehouse_ref: Mapped[str] = mapped_column(String(64), default="")
    np_warehouse_type: Mapped[str] = mapped_column(String(16), default="")  # Branch|Postomat
    # Експрес-накладна (ЕН).
    np_waybill_number: Mapped[str] = mapped_column(String(32), default="")
    np_waybill_ref: Mapped[str] = mapped_column(String(64), default="")
    # Сума до знижки, сама знижка та фінальна ціна.
    subtotal: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    # Знижка на товар (сума по всіх позиціях) — знімок.
    product_discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    discount_amount: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    discount_source: Mapped[str] = mapped_column(String(16), default="")  # ""|"account"|"code"
    discount_label: Mapped[str] = mapped_column(String(255), default="")  # знімок опису знижки
    discount_code_id: Mapped[int | None] = mapped_column(ForeignKey("discount_codes.id", ondelete="SET NULL"))
    total_price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    user: Mapped["User"] = relationship(back_populates="orders")
    status: Mapped["OrderStatus"] = relationship()
    discount_code: Mapped["DiscountCode | None"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    status_logs: Mapped[list["OrderStatusLog"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusLog.created_at",
    )


class OrderStatusLog(Base):
    """Журнал переходів статусу замовлення (знімок назв + час).

    Назви зберігаються рядком — журнал переживає перейменування/видалення статусів.
    from_status=None => початкове створення замовлення.
    """

    __tablename__ = "order_status_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    from_status: Mapped[str | None] = mapped_column(String(255))
    to_status: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    order: Mapped["Order"] = relationship(back_populates="status_logs")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"))
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(255))
    base_price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    line_total: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)

    order: Mapped["Order"] = relationship(back_populates="items")
    modifications: Mapped[list["OrderItemModification"]] = relationship(
        back_populates="item", cascade="all, delete-orphan"
    )


class OrderItemModification(Base):
    __tablename__ = "order_item_modifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id", ondelete="CASCADE"))
    modification_value_id: Mapped[int | None] = mapped_column(ForeignKey("modification_values.id"))
    label: Mapped[str] = mapped_column(String(512))  # "Колір: Червоний" — знімок
    custom_text: Mapped[str | None] = mapped_column(Text)
    price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), default=ZERO)

    item: Mapped["OrderItem"] = relationship(back_populates="modifications")


# --- Налаштування магазину (єдиний рядок, id=1) -----------------------------
# Порожнє значення => використовується env-дефолт (див. app/np_settings.py).
class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    # Nova Poshta
    np_api_key: Mapped[str] = mapped_column(String(64), default="")
    np_sender_ref: Mapped[str] = mapped_column(String(64), default="")
    np_sender_contact_ref: Mapped[str] = mapped_column(String(64), default="")
    np_sender_phone: Mapped[str] = mapped_column(String(32), default="")
    np_sender_city_ref: Mapped[str] = mapped_column(String(64), default="")
    np_sender_city_name: Mapped[str] = mapped_column(String(255), default="")
    np_sender_warehouse_ref: Mapped[str] = mapped_column(String(64), default="")
    np_sender_warehouse_name: Mapped[str] = mapped_column(String(255), default="")
    np_sender_warehouse_type: Mapped[str] = mapped_column(String(16), default="")
    np_default_weight: Mapped[str] = mapped_column(String(16), default="")
    np_seat_width: Mapped[str] = mapped_column(String(16), default="")
    np_seat_length: Mapped[str] = mapped_column(String(16), default="")
    np_seat_height: Mapped[str] = mapped_column(String(16), default="")
    np_payer_type: Mapped[str] = mapped_column(String(16), default="")  # Recipient|Sender
    # Нумерація замовлень
    order_start_number: Mapped[int] = mapped_column(Integer, default=1)
