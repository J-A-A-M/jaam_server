# JAAM Store — Інтернет-магазин

Мікросервіс інтернет-магазину для JAAM. Побудований на **Starlette** + **SQLAlchemy** + **SQLite** (за замовчуванням).

## Особливості

- **REST API** для товарів, категорій і замовлень
- **Адмін-панель** (веб-інтерфейс)
- **Система користувачів**: реєстрація, вхід, ролі (користувач/адмін)
- **SQLite** за замовчуванням; підтримка інших SQL-баз через `DATABASE_URL`
- **Сесії** на базі JWT (безпечні cookies)
- **Демо-каталог** для розробки

## Локальний запуск

### Підготовка

```bash
cd store/
python -m venv .venv
source .venv/bin/activate  # чи .venv\Scripts\activate на Windows
pip install -r requirements.txt
```

### Ініціалізація БД з демо-даними

```bash
# Створити SQLite БД та заповнити демо-товарами
python -m app.seed_demo
```

### Запуск

```bash
# Робоча директорія — там де лежить папка `app/`
python -m app.main
```

Відкрити в браузері: `http://localhost:8090`

## Env-змінні

| Змінна | Тип | Умовчання | Опис |
|--------|-----|-----------|------|
| `PORT` | int | `8090` | Порт HTTP-сервера |
| `HOST` | str | `0.0.0.0` | IP-адреса, на якій слухає сервер |
| `LOGGING` | str | `INFO` | Рівень логування (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `SESSION_SECRET` | str | `dev-insecure-secret-change-me` | Секретний ключ для сесій (сніданки JWT) |
| `MASTER_KEY` | str | `change-me-master-admin-key` | Майстер-ключ адміністратора |
| `DATABASE_URL` | str | `sqlite:///./var/store.db` | URL підключення до БД (SQLite, PostgreSQL, MySQL і т.д.) |
| `STORE_DB_PATH` | str | `./var/store.db` | Шлях до SQLite-файлу (ігнорується якщо заданий `DATABASE_URL`) |
| `DATA_DIR` | str | `./data` | Директорія для статичних даних (nova_poshta_branches.json) |

## Як стати адміністратором

1. Створити/увійти в акаунт на http://localhost:8090
2. Перейти на `/admin/become`
3. Ввести `MASTER_KEY` (за замовчуванням: `change-me-master-admin-key`)
4. Отримати адмін-доступ до панелі

## Перехід на іншу SQL-базу

За замовчуванням використовується **SQLite**. Щоб перейти на PostgreSQL, MySQL або іншу:

1. Встановити драйвер:
   ```bash
   # PostgreSQL
   pip install psycopg
   
   # MySQL
   pip install pymysql
   ```

2. Задати `DATABASE_URL`:
   ```bash
   # PostgreSQL
   export DATABASE_URL="postgresql+psycopg://user:password@localhost/store_db"
   
   # MySQL
   export DATABASE_URL="mysql+pymysql://user:password@localhost/store_db"
   ```

3. Запустити додавання драйвера в `requirements.txt` (разовим оновленням для docker-образу).

## Docker-розгортання

### Швидко

```bash
./redeploy_store.sh \
    -mk "мій-супер-секретний-ключ" \
    -ss "мій-супер-секретний-сессійний-ключ" \
    -p 8090 \
    -l INFO
```

### Розширено з PostgreSQL

```bash
./redeploy_store.sh \
    -mk "мій-супер-секретний-ключ" \
    -ss "мій-супер-секретний-сессійний-ключ" \
    -p 8090 \
    -l INFO \
    -db "postgresql+psycopg://user:pass@postgres-host/store_db"
```

### Аргументи скрипта

- `-p, --port` — Зовнішній порт (default: 8090)
- `-mk, --master-key` — Майстер-ключ адміна (ОБОВ'ЯЗКОВО для production)
- `-ss, --session-secret` — Секретний ключ сесій (ОБОВ'ЯЗКОВО для production)
- `-l, --logging` — Рівень логування (default: INFO)
- `-db, --database-url` — URL БД; якщо не задано — SQLite в volume

### Volume для зберігання БД

SQLite-файл зберігається на volume `/store_data:/data` всередині контейнера (`/data/store.db`). Це гарантує збереження замовлень і товарів між редеплоями.

### Docker-мережа

Контейнер запускається на мережі `jaam` з іменем `map_store`. Інші сервіси мають доступ через `http://map_store:8090`.

## Nginx-конфіг

Сніпет для додання в nginx-конфіг знаходиться в `nginx_store.conf`. Скопіюй блоки у основний `nginx.conf` для SSL/Cloudflare-підтримки.

Маршрут: `store.jaam.net.ua` → `http://map_store:8090` (всередині Docker-мережи).

## Структура проєкту

```
store/
├── app/                      # Пакет застосунку
│   ├── __init__.py
│   ├── main.py              # Точка входу
│   ├── config.py            # Конфіг (env-змінні)
│   ├── db.py                # Сесія SQLAlchemy
│   ├── models.py            # ORM-моделі
│   ├── core.py              # Бізнес-логіка
│   ├── security.py          # Аутентифікація
│   ├── templating.py        # Jinja2
│   ├── seed_demo.py         # Демо-каталог
│   ├── routes/              # API-маршрути
│   ├── static/              # CSS, JS, зображення
│   └── templates/           # HTML-шаблони
├── data/                     # Статичні дані
│   └── nova_poshta_branches.json
├── var/                      # Runtime (БД, логи) — volume
│   └── store.db
├── Dockerfile               # Docker-образ
├── redeploy_store.sh        # Скрипт розгортання
├── nginx_store.conf         # Nginx-блоки
├── requirements.txt         # Python-залежності
└── README.md               # Цей файл
```

## Розробка

### Структура маршрутів

```python
# app/routes/products.py, app/routes/orders.py, app/routes/auth.py, app/routes/admin.py
```

Кожен модуль — окремий набір маршрутів, підключений до основного Starlette-додатку.

### Сидування демо-даних

```bash
python -m app.seed_demo
```

Заповнює БД демо-товарами, категоріями й тестовими акаунтами (обережно на production!).

## Проблеми й FAQ

**P: SQLite виглядає недостатньо для production?**
Д: На малі навантаження (сотні замовлень) SQLite добре справляється. Для більших обсягів переходь на PostgreSQL через `DATABASE_URL`.

**P: Як залогувати всіх користувачів при оновленні SECRET?**
Д: SESSION_SECRET — це ключ шифрування. При змін — всі сесії стають невалідні автоматично. Користувачі мають заново увійти.

**P: Де знайти логи контейнера?**
Д: `docker logs map_store` або `docker logs -f map_store` (live).

## Додаткові команди

```bash
# Вхід у контейнер
docker exec -it map_store bash

# Перевірка статусу
docker ps | grep map_store

# Перемонтування образу
docker pull map_store  # якщо з реєстру
docker build -t map_store -f store/Dockerfile ..

# Зупинення
docker stop map_store
docker rm map_store
```

## Документація

- [Starlette docs](https://www.starlette.io/)
- [SQLAlchemy docs](https://docs.sqlalchemy.org/)
- [Jinja2 docs](https://jinja.palletsprojects.com/)

---

**Автор**: JAAM Team  
**Ліцензія**: MIT
