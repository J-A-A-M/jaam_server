"""In-memory обмеження спроб логіна (захист від брутфорсу/password-spray).

Ключ — IP клієнта, тож і підбір пароля до одного логіна, і перебір логінів з
одного IP підпадають під спільний ліміт. Після MAX_ATTEMPTS невдалих спроб у
вікні WINDOW_SECONDS IP блокується на LOCKOUT_SECONDS. Успішний вхід скидає лічильник.

Обмеження: стан у пам'яті процесу (як і webauthn-challenges) — при кількох
воркерах/репліках рахується окремо. Для поточного single-process деплою достатньо.
"""

import time

MAX_ATTEMPTS = 10
WINDOW_SECONDS = 300  # 5 хв — вікно накопичення невдалих спроб
LOCKOUT_SECONDS = 600  # 10 хв блокування після перевищення

# key -> {"count": int, "window_start": float, "locked_until": float}
_attempts: dict[str, dict] = {}


def _now() -> float:
    return time.time()


def _purge(now: float) -> None:
    """Прибирає застарілі записи (вікно вийшло і блокування зняте)."""
    for k in [k for k, e in _attempts.items() if e["locked_until"] <= now and now - e["window_start"] > WINDOW_SECONDS]:
        del _attempts[k]


def retry_after(key: str) -> int:
    """Повертає 0, якщо спроба дозволена, або кількість секунд до розблокування."""
    e = _attempts.get(key)
    if not e:
        return 0
    now = _now()
    if e["locked_until"] > now:
        return int(e["locked_until"] - now) + 1
    return 0


def register_failure(key: str) -> None:
    now = _now()
    _purge(now)
    e = _attempts.get(key)
    if not e or now - e["window_start"] > WINDOW_SECONDS:
        e = {"count": 0, "window_start": now, "locked_until": 0.0}
    e["count"] += 1
    if e["count"] >= MAX_ATTEMPTS:
        e["locked_until"] = now + LOCKOUT_SECONDS
    _attempts[key] = e


def reset(key: str) -> None:
    _attempts.pop(key, None)
