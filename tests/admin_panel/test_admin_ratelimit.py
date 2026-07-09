"""Тести обмеження спроб логіна (app/ratelimit.py)."""

import app.ratelimit as rl


def test_fresh_key_is_allowed():
    rl.reset("fresh-ip")
    assert rl.retry_after("fresh-ip") == 0


def test_lockout_after_max_attempts(monkeypatch):
    clock = {"v": 1000.0}
    monkeypatch.setattr(rl, "_now", lambda: clock["v"])
    key = "10.0.0.1"
    rl.reset(key)

    # До ліміту — ще дозволено
    for _ in range(rl.MAX_ATTEMPTS - 1):
        rl.register_failure(key)
    assert rl.retry_after(key) == 0

    # Досягли ліміту — заблоковано
    rl.register_failure(key)
    wait = rl.retry_after(key)
    assert wait > 0

    # Після завершення блокування — знову дозволено
    clock["v"] += rl.LOCKOUT_SECONDS + 1
    assert rl.retry_after(key) == 0


def test_reset_clears_counter(monkeypatch):
    clock = {"v": 0.0}
    monkeypatch.setattr(rl, "_now", lambda: clock["v"])
    key = "10.0.0.2"
    for _ in range(rl.MAX_ATTEMPTS):
        rl.register_failure(key)
    assert rl.retry_after(key) > 0
    rl.reset(key)
    assert rl.retry_after(key) == 0


def test_window_resets_counter(monkeypatch):
    clock = {"v": 0.0}
    monkeypatch.setattr(rl, "_now", lambda: clock["v"])
    key = "10.0.0.3"
    rl.reset(key)
    # Кілька спроб, але менше за ліміт
    for _ in range(rl.MAX_ATTEMPTS - 1):
        rl.register_failure(key)
    # Минув час вікна — лічильник має обнулитись, блокування не настає
    clock["v"] += rl.WINDOW_SECONDS + 1
    rl.register_failure(key)
    assert rl.retry_after(key) == 0
