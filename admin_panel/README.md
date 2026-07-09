# JAAM Admin Panel

Єдина адмін-панель моніторингу мап: агрегує стан клієнтів з одного або кількох
`websocket_server` (через їхні Redis), зберігає реєстр пристроїв за `chip_id` та історію
у Postgres, показує дашборд/список/карту/аналітику. Авторизація — JWT у httpOnly cookie.

## Архітектура

- **backend/** — FastAPI + SQLAlchemy(async) + фоновий **collector**.
  - `app/collector.py` — кожні `COLLECT_INTERVAL` с сканує `websocket:clients:*` на всіх
    налаштованих Redis, дедуплікує за `chip_id` (найновіший `connect_time`), upsert у Postgres,
    веде сесії та події online/offline/firmware_change/geo_change.
  - `app/routes/` — `/api/auth`, `/api/overview`, `/api/devices`, `/api/inventory`, `/api/geo`,
    `/api/servers`, `/api/stream` (SSE).

### Реєстр JAAM (`jaam_maps`)

Таблиця офіційно проданих мап: `chip_id`, `hw_version`, `is_prototype`, `order_number` (опц.),
`customer_info` (вільний текст). Ключ `chip_id` склеюється з `devices`, тож у списку мап,
деталях і дашборді видно розбивку **офіційна JAAM vs самозбірка** (самозбірки в реєстр не
потрапляють, але видно онлайн). Сторінка «Реєстр JAAM» дає CRUD (додати/редагувати/видалити),
пошук і фільтр за станом (онлайн / офлайн / ніколи не був онлайн).

- **frontend/** — React + Vite + TS + Tailwind (shadcn-стиль) + Recharts + Leaflet.
- **Dockerfile** — multi-stage: збірка SPA → FastAPI віддає API та статику з `/app/static`.

## Змінні оточення (backend)

| Env | За замовч. | Опис |
|-----|-----------|------|
| `DATABASE_URL` | `postgresql+asyncpg://jaam:jaam@postgres:5432/jaam_admin` | Postgres |
| `REDIS_HOSTS` | — | JSON `[{host,port,password,db,name}]` для кількох серверів |
| `REDIS_HOST`/`REDIS_PASSWORD`/`REDIS_DB` | `redis`/`redis`/`0` | одиночний Redis (якщо немає `REDIS_HOSTS`) |
| `JWT_SECRET` | `change-me-in-production` | секрет підпису токенів |
| `ADMIN_USER`/`ADMIN_PASSWORD` | `admin`/`jaam_rocks` | сідовий адмін (створюється лише якщо таблиця users порожня) |
| `COLLECT_INTERVAL` | `20` | період скану Redis, с |
| `OFFLINE_AFTER_SECONDS` | `150` | поріг офлайну (> Redis TTL 120с) |
| `PORT` | `8099` | порт API |

## Користувачі

Перший запуск сідає адміна **`admin` / `jaam_rocks`**. Після входу: сторінка «Користувачі»
(лише для ролі `admin`) — створити потрібних користувачів (`admin` — повний доступ, `viewer` —
лише перегляд), тоді **видалити дефолтного `admin`**. Не можна видалити останнього користувача.

## Розгортання (в інфраструктурі JAAM)

Через GitHub Actions (`workflow_dispatch`): спершу **Deploy Postgres**, тоді **Deploy Admin Panel**,
тоді **Deploy Nginx**. Або вручну:

```bash
./redeploy_postgres.sh -w <db_password>
./redeploy_admin_panel.sh \
  -s <jwt_secret> \
  -d 'postgresql+asyncpg://jaam:<db_password>@postgres:5432/jaam_admin'
# кілька серверів (мультисервер):
#   -rh '[{"host":"redis","name":"prod"},{"host":"redis2","name":"prod2"}]'
```

**GitHub-секрети** (додати в repo): `ADMIN_PANEL_DB_PASSWORD`, `ADMIN_PANEL_JWT_SECRET`
(SSH та `CLOUD_REDIS_*` уже є). Креди адміна дефолтні (`admin`/`jaam_rocks`) — окремих секретів
не потребують. Мультисервер: input `redis_hosts` у workflow або секрет із JSON.

Nginx-маршрут `admin.jaam.net.ua` вже додано в `nginx/nginx.conf` (проксі на `jaam_admin_panel:8099`).

## Локальна розробка

```bash
# backend
cd backend && pip install -r requirements.txt
DATABASE_URL=postgresql+asyncpg://jaam:jaam@localhost:5432/jaam_admin \
REDIS_HOST=localhost python -m uvicorn app.main:app --reload --port 8099

# frontend (проксі /api → :8099)
cd frontend && npm install && npm run dev
```
