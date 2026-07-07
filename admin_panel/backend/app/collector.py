"""Фоновий збирач: періодично сканує Redis-и, зводить стан мап у Postgres.

Ключова відмінність від maps_online/device_map: дедуплікація за стабільним chip_id
(беремо запис із найновішим connect_time), персистентність (офлайн-мапи лишаються в БД),
історія сесій та подій.
"""

import asyncio
import datetime
import json
import re
import logging

from sqlalchemy import select, update

from .config import COLLECT_INTERVAL, OFFLINE_AFTER_SECONDS
from .db import SessionLocal
from .models import Device, DeviceEvent, DeviceSession, utcnow
from .redis_util import RedisServer, scan_clients

logger = logging.getLogger("admin_panel.collector")


def _parse_location(loc: str | None) -> tuple[float | None, float | None]:
    if not loc or loc == "0,0":
        return None, None
    try:
        lat_s, lon_s = loc.split(",")
        return float(lat_s), float(lon_s)
    except (ValueError, AttributeError):
        return None, None


def _strip_chip_suffix(version: str) -> str:
    """Прибирає суфікси -c3/-s3 з версії прошивки (вони зберігаються окремо в hw_type)."""
    return re.sub(r"[-_](c3|s3)$", "", version, flags=re.IGNORECASE)


def _split_firmware(raw: str | None) -> tuple[str | None, str | None]:
    """Розбиває 'version_id' → (version, id). Якщо '_' немає — (raw, None)."""
    if raw and "_" in raw:
        version, fid = raw.split("_", 1)
        return _strip_chip_suffix(version), fid
    return (_strip_chip_suffix(raw) if raw else raw), None


def _hw_type(value: dict) -> str | None:
    for key in ("hardware", "legacy", "hw"):
        v = value.get(key)
        if v not in (None, ""):
            return str(v)
    firmware = (value.get("firmware") or "").lower()
    if firmware:
        if "c3" in firmware:
            return "ESP32-C3"
        if "s3" in firmware:
            return "ESP32-S3"
        return "ESP32"
    return None


def _truncate(value: str | None, max_len: int) -> str | None:
    """Обрізає рядок до максимальної довжини."""
    if value is None:
        return None
    s = str(value)
    return s[:max_len] if len(s) > max_len else s


def dedup_by_chip_id(records: list[tuple[str, dict]]) -> dict[str, dict]:
    """records: список (server_name, value). Повертає chip_id -> value з найновішим connect_time."""
    best: dict[str, dict] = {}
    for server_name, value in records:
        chip_id = value.get("chip_id")
        if not chip_id or chip_id == "unknown":
            continue
        value = {**value, "_server": server_name}
        prev = best.get(chip_id)
        if prev is None or (value.get("connect_time") or "") > (prev.get("connect_time") or ""):
            best[chip_id] = value
    return best


async def _add_event(session, chip_id: str, event_type: str, details: dict | None = None) -> None:
    session.add(
        DeviceEvent(
            chip_id=chip_id,
            type=event_type,
            details=json.dumps(details, ensure_ascii=False) if details else None,
        )
    )


async def _apply_snapshot(
    session, chip_id: str, value: dict, now: datetime.datetime, devices_cache: dict, server_tz: str = "Europe/Kyiv"
) -> bool:
    firmware, firmware_id = _split_firmware(value.get("firmware"))
    server_name = value.get("_server")
    connect_time = value.get("connect_time")
    lat, lon = _parse_location(value.get("location"))

    device = devices_cache.get(chip_id)
    is_new = device is None
    was_offline = is_new or not device.is_online
    prev_firmware = None if is_new else device.firmware
    prev_firmware_id = None if is_new else device.firmware_id
    prev_location = None if is_new else device.location
    prev_city = None if is_new else device.city
    prev_region = None if is_new else device.region
    prev_connect = None if is_new else device.connect_time
    prev_ip = None if is_new else device.last_ip

    if is_new:
        device = Device(chip_id=chip_id, first_seen=now)
        session.add(device)

    device.firmware = _truncate(firmware, 64)
    device.firmware_id = _truncate(firmware_id, 128)
    device.hw_type = _truncate(_hw_type(value) or device.hw_type, 32)
    device.is_online = True
    device.last_seen = now
    device.last_online_at = now
    device.connect_time = _truncate(connect_time, 32)
    device.last_ip = _truncate(value.get("ip") or device.last_ip, 64)
    device.city = _truncate(value.get("city"), 128)
    device.region = _truncate(value.get("region"), 128)
    device.country = _truncate(value.get("country"), 64)
    device.timezone = _truncate(value.get("timezone"), 64)
    device.org = _truncate(value.get("org"), 256)
    device.location = _truncate(value.get("location"), 64)
    device.lat, device.lon = lat, lon
    latency = value.get("latency")
    device.latency = latency if isinstance(latency, int) else device.latency
    sc = value.get("secure_connection")
    device.secure_connection = (sc.lower() == "true") if isinstance(sc, str) else bool(sc) if sc is not None else None
    device.last_server = _truncate(server_name, 64)

    # Події
    if is_new:
        await _add_event(session, chip_id, "first_seen", {"firmware": firmware})
    if was_offline:
        await _add_event(session, chip_id, "online", {"server": server_name})
    if not is_new and prev_firmware and firmware and prev_firmware != firmware:
        await _add_event(session, chip_id, "firmware_change", {"from": prev_firmware, "to": firmware})
    if not is_new and prev_firmware_id != firmware_id and (prev_firmware_id or firmware_id):
        await _add_event(session, chip_id, "firmware_id_change", {"from": prev_firmware_id, "to": firmware_id})
    if not is_new and prev_location and device.location and prev_location != device.location:

        def _geo_label(city, region):
            parts = [p for p in (city, region) if p]
            return ", ".join(parts) if parts else None

        await _add_event(
            session,
            chip_id,
            "geo_change",
            {"from": _geo_label(prev_city, prev_region), "to": _geo_label(value.get("city"), value.get("region"))},
        )
    new_ip = value.get("ip")
    if not is_new and not was_offline and prev_ip and new_ip and prev_ip != new_ip:
        await _add_event(session, chip_id, "ip_change", {"from": prev_ip, "to": new_ip})

    # Сесія: нова, якщо пристрій був офлайн або змінився connect_time
    new_session_needed = was_offline or (connect_time and connect_time != prev_connect)
    should_close_sessions = was_offline

    # Перевірка: якщо пристрій онлайн, але немає активної сесії, створити нову
    if not new_session_needed and not was_offline:
        # Перевіримо чи є активна сесія для цього пристрою
        active_session = await session.scalar(
            select(DeviceSession).where(DeviceSession.chip_id == chip_id, DeviceSession.ended_at.is_(None))
        )
        if not active_session:
            new_session_needed = True

    if new_session_needed:
        session.add(
            DeviceSession(
                chip_id=chip_id,
                server_name=_truncate(server_name, 64),
                connect_time=_truncate(connect_time, 32),
                started_at=now,
                firmware=_truncate(firmware, 64),
                firmware_id=_truncate(firmware_id, 128),
                ip=_truncate(value.get("ip"), 64),
                city=_truncate(value.get("city"), 128),
                region=_truncate(value.get("region"), 128),
            )
        )
    return should_close_sessions


async def _close_open_sessions(session, chip_ids: set[str], now: datetime.datetime) -> None:
    if not chip_ids:
        return
    result = await session.execute(
        select(DeviceSession).where(DeviceSession.chip_id.in_(chip_ids), DeviceSession.ended_at.is_(None))
    )
    for s in result.scalars().all():
        s.ended_at = now
        started = s.started_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=datetime.timezone.utc)
        s.duration_sec = int((now - started).total_seconds()) if started else None


async def _mark_stale_offline(session, seen_chip_ids: set[str], now: datetime.datetime) -> int:
    """Позначає офлайн ті пристрої, яких не бачили довше за поріг."""
    threshold = now - datetime.timedelta(seconds=OFFLINE_AFTER_SECONDS)
    result = await session.execute(select(Device).where(Device.is_online.is_(True), Device.last_seen < threshold))
    devices_to_close = []
    count = 0
    for device in result.scalars().all():
        if device.chip_id in seen_chip_ids:
            continue
        device.is_online = False
        device.last_online_at = device.last_seen
        devices_to_close.append((device.chip_id, device.last_seen or now))
        await _add_event(session, device.chip_id, "offline", None)
        count += 1

    # Bulk close all open sessions for devices marked offline
    if devices_to_close:
        chips_to_close = {chip_id for chip_id, _ in devices_to_close}
        await _close_open_sessions(session, chips_to_close, now)

    return count


async def collect_once(servers: list[RedisServer]) -> dict:
    now = utcnow()
    # Snapshot the list to prevent issues if servers are mutated during collection
    servers_snapshot = list(servers)
    # Build server_name -> timezone map for later use in _apply_snapshot
    servers_tz = {s.name: s.timezone for s in servers_snapshot}
    scans = await asyncio.gather(*[scan_clients(s.client) for s in servers_snapshot], return_exceptions=True)
    records: list[tuple[str, dict]] = []
    per_server: dict[str, int] = {}
    for server, result in zip(servers_snapshot, scans):
        if isinstance(result, Exception):
            logger.error("Помилка скану Redis %s: %s", server.name, result)
            per_server[server.name] = -1
            continue
        per_server[server.name] = len(result)
        for value in result:
            records.append((server.name, value))

    deduped = dedup_by_chip_id(records)

    async with SessionLocal() as session:
        # Bulk-load existing devices to avoid N+1 queries
        if deduped:
            result = await session.execute(select(Device).where(Device.chip_id.in_(deduped.keys())))
            devices_cache = {d.chip_id: d for d in result.scalars().all()}
        else:
            devices_cache = {}

        chips_needing_session_close = set()
        for chip_id, value in deduped.items():
            try:
                server_name = value.get("_server")
                tz = servers_tz.get(server_name, "Europe/Kyiv")
                needs_close = await _apply_snapshot(session, chip_id, value, now, devices_cache, tz)
                if needs_close:
                    chips_needing_session_close.add(chip_id)
            except Exception:
                logger.exception("Помилка при обробці пристрою %s, пропускаємо", chip_id)
                await session.rollback()

        # Close open sessions for devices that need new ones (single bulk query)
        await _close_open_sessions(session, chips_needing_session_close, now)

        offline = await _mark_stale_offline(session, set(deduped.keys()), now)
        await session.commit()

    stats = {
        "online_unique": len(deduped),
        "marked_offline": offline,
        "per_server": per_server,
    }
    logger.info("Цикл збору: %s", stats)
    return stats


async def run_collector(servers: list[RedisServer], stop_event: asyncio.Event) -> None:
    logger.info("Collector стартував, інтервал %sс", COLLECT_INTERVAL)
    while not stop_event.is_set():
        try:
            await collect_once(servers)
        except Exception:  # noqa: BLE001
            logger.exception("Помилка в циклі збору")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=COLLECT_INTERVAL)
        except asyncio.TimeoutError:
            pass
