"""Тести чистих хелперів дашборда (app/overview.py)."""

import datetime

from app.routes.overview import _connect_time_to_utc, _duration_label, _median_label


def test_duration_label():
    assert _duration_label(0) == "0хв"
    assert _duration_label(45) == "45хв"
    assert _duration_label(60) == "1г"
    assert _duration_label(90) == "1г 30хв"


def test_median_label():
    assert _median_label([]) == "—"
    assert _median_label([10]) == "10хв"
    assert _median_label([10, 20]) == "15хв"  # середнє двох центральних
    assert _median_label([10, 20, 30]) == "20хв"


def test_connect_time_to_utc_with_z():
    dt = _connect_time_to_utc("2026-01-15T10:00:00Z")
    assert dt == datetime.datetime(2026, 1, 15, 10, 0, 0, tzinfo=datetime.timezone.utc)


def test_connect_time_to_utc_invalid():
    assert _connect_time_to_utc(None) is None
    assert _connect_time_to_utc("") is None
    assert _connect_time_to_utc("not-a-date") is None
