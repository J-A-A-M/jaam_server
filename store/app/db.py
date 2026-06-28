"""Налаштування БД: engine, сесії, ініціалізація, ідемпотентний сід."""

from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL

# SQLite потребує check_same_thread=False (Starlette виконує sync-ендпоінти в
# пулі потоків). Для інших діалектів цей аргумент ігнорується.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args, future=True)

# Вмикаємо foreign keys для SQLite (ondelete CASCADE інакше не працює).
if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


@contextmanager
def get_db():
    """Контекст-менеджер сесії: commit при успіху, rollback при помилці."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# Ролі фіксованих статусів — стабільні ідентифікатори (назву можна змінювати).
ROLE_NEW = "new"
ROLE_DONE = "done"
ROLE_CANCELLED = "cancelled"

# Фіксовані статуси (task: "нове" "завершене" та "скасоване" — їх не можна видаляти).
FIXED_STATUSES = [
    {"name": "нове", "position": 0, "role": ROLE_NEW},
    {"name": "завершене", "position": 900, "role": ROLE_DONE},
    {"name": "скасоване", "position": 1000, "role": ROLE_CANCELLED},
]
STATUS_NEW = "нове"
STATUS_DONE = "завершене"
STATUS_CANCELLED = "скасоване"


def _ensure_columns():
    """Ідемпотентно додає нові колонки до наявних таблиць.

    create_all() створює відсутні ТАБЛИЦІ, але не додає КОЛОНКИ до наявних.
    Для нових полів на старій БД (volume переживає redeploy) — ALTER TABLE.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    # (таблиця, колонка, DDL-тип) — лише адитивні, безпечні зміни.
    wanted = [
        ("orders", "product_discount_amount", "NUMERIC(10, 2) DEFAULT 0"),
        ("product_discounts", "starts_at", "DATETIME"),
        ("product_discounts", "sticker_id", "INTEGER"),
        ("order_statuses", "role", "VARCHAR(16) DEFAULT ''"),
        ("order_statuses", "color", "VARCHAR(16) DEFAULT '#007bff'"),
        ("order_statuses", "text_color", "VARCHAR(16) DEFAULT '#ffffff'"),
    ]
    existing_tables = set(inspector.get_table_names())
    with engine.begin() as conn:
        for table, column, ddl in wanted:
            if table not in existing_tables:
                continue
            cols = {c["name"] for c in inspector.get_columns(table)}
            if column not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def init_db():
    """Створює таблиці та ідемпотентно сідить фіксовані статуси."""
    # імпорт моделей реєструє їх у Base.metadata
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_columns()

    with get_db() as db:
        from app.models import OrderStatus

        existing = {s.name: s for s in db.query(OrderStatus).all()}
        for spec in FIXED_STATUSES:
            if spec["name"] not in existing:
                db.add(
                    OrderStatus(
                        name=spec["name"],
                        is_fixed=True,
                        role=spec["role"],
                        position=spec["position"],
                    )
                )
        db.flush()

        # Backfill ролі для наявних фіксованих статусів (стара БД без role).
        by_name = {spec["name"]: spec["role"] for spec in FIXED_STATUSES}
        for s in db.query(OrderStatus).filter(OrderStatus.is_fixed.is_(True)).all():
            if not s.role and s.name in by_name:
                s.role = by_name[s.name]

        # Рядок налаштувань (id=1), щоб load_np() не писав під час читання.
        from app.config import ORDER_START_NUMBER
        from app.models import Settings

        if db.get(Settings, 1) is None:
            db.add(Settings(id=1, order_start_number=ORDER_START_NUMBER))
