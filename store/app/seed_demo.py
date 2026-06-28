"""Демо-наповнення каталогу для ручного тестування.

Запуск:  python -m app.seed_demo
Ідемпотентно для статусів (через init_db); товари додаються лише якщо їх немає.
"""

import decimal

from app.db import get_db, init_db
from app.models import Category, Modification, ModificationValue, Product


def run():
    init_db()
    with get_db() as db:
        if db.query(Product).first():
            print("Каталог уже наповнено — пропускаю.")
            return

        # Розділи (вкладені)
        maps = Category(name="Мапи JAAM")
        accessories = Category(name="Аксесуари")
        db.add_all([maps, accessories])
        db.flush()
        cases = Category(name="Корпуси", parent_id=accessories.id)
        db.add(cases)
        db.flush()

        # Модифікації
        color = Modification(name="Колір корпусу")
        db.add(color)
        db.flush()
        color.values = [
            ModificationValue(label="Чорний", price=decimal.Decimal("0.00"), position=0),
            ModificationValue(label="Білий", price=decimal.Decimal("150.00"), position=1),
            ModificationValue(label="Дерево", price=decimal.Decimal("500.00"), position=2),
        ]

        engraving = Modification(name="Гравіювання")
        db.add(engraving)
        db.flush()
        engraving.values = [
            ModificationValue(label="Без гравіювання", price=decimal.Decimal("0.00"), position=0),
            ModificationValue(
                label="Власний текст",
                price=decimal.Decimal("250.00"),
                is_custom_text=True,
                position=1,
            ),
        ]

        # Товари
        jaam3 = Product(
            name="Мапа JAAM 3",
            description="Світлодіодна мапа повітряних тривог України.",
            base_price=decimal.Decimal("3500.00"),
            position=0,
            show_on_home=True,
        )
        jaam3.categories = [maps]
        jaam3.modifications = [color, engraving]

        jaam_mini = Product(
            name="Мапа JAAM Mini",
            description="Компактна версія мапи.",
            base_price=decimal.Decimal("2200.00"),
            position=1,
            show_on_home=True,
        )
        jaam_mini.categories = [maps]
        jaam_mini.modifications = [color]

        db.add_all([jaam3, jaam_mini])
        print("Демо-каталог створено.")


if __name__ == "__main__":
    run()
