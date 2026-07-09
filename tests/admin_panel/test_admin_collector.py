"""Тести чистих хелперів collector-а (app/collector.py)."""

from app.collector import (
    _hw_type,
    _parse_location,
    _split_firmware,
    _strip_chip_suffix,
    _truncate,
    dedup_by_chip_id,
)


def test_parse_location():
    assert _parse_location("50.45,30.52") == (50.45, 30.52)
    assert _parse_location("0,0") == (None, None)
    assert _parse_location(None) == (None, None)
    assert _parse_location("garbage") == (None, None)


def test_strip_chip_suffix():
    assert _strip_chip_suffix("4.30.0-c3") == "4.30.0"
    assert _strip_chip_suffix("4.30.0_s3") == "4.30.0"
    assert _strip_chip_suffix("4.30.0-C3") == "4.30.0"  # регістронезалежно
    assert _strip_chip_suffix("4.30.0") == "4.30.0"


def test_split_firmware():
    assert _split_firmware("4.30.0_abc123") == ("4.30.0", "abc123")
    assert _split_firmware("4.30.0-c3_id7") == ("4.30.0", "id7")  # суфікс знято з версії
    assert _split_firmware("4.30.0") == ("4.30.0", None)
    assert _split_firmware(None) == (None, None)


def test_hw_type():
    assert _hw_type({"firmware": "4.30_c3"}) == "ESP32-C3"
    assert _hw_type({"firmware": "4.30_s3"}) == "ESP32-S3"
    assert _hw_type({"firmware": "4.30"}) == "ESP32"
    assert _hw_type({"hardware": "custom-board"}) == "custom-board"
    assert _hw_type({}) is None


def test_truncate():
    assert _truncate(None, 5) is None
    assert _truncate("short", 10) == "short"
    assert _truncate("0123456789", 4) == "0123"


def test_dedup_by_chip_id_keeps_newest():
    records = [
        ("srv1", {"chip_id": "aa", "connect_time": "2026-01-01T10:00:00"}),
        ("srv2", {"chip_id": "aa", "connect_time": "2026-01-02T10:00:00"}),  # новіший
        ("srv1", {"chip_id": "bb", "connect_time": "2026-01-01T10:00:00"}),
    ]
    result = dedup_by_chip_id(records)
    assert set(result.keys()) == {"aa", "bb"}
    assert result["aa"]["connect_time"] == "2026-01-02T10:00:00"
    assert result["aa"]["_server"] == "srv2"


def test_dedup_skips_unknown_and_missing():
    records = [
        ("srv1", {"chip_id": "unknown", "connect_time": "x"}),
        ("srv1", {"connect_time": "x"}),  # немає chip_id
        ("srv1", {"chip_id": "ok", "connect_time": "y"}),
    ]
    result = dedup_by_chip_id(records)
    assert list(result.keys()) == ["ok"]
