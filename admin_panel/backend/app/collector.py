"""Фоновий збирач: періодично сканує Redis-и, зводить стан мап у Postgres.

Ключова відмінність від maps_online/device_map: дедуплікація за стабільним chip_id
(беремо запис із найновішим connect_time), персистентність (офлайн-мапи лишаються в БД),
історія сесій та подій.
"""

import asyncio
import datetime
import json
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


def _split_firmware(raw: str | None) -> tuple[str | None, str | None]:
    """Розбиває 'version_id' → (version, id). Якщо '_' немає — (raw, None)."""
    if raw and "_" in raw:
        version, fid = raw.split("_", 1)
        return version, fid
    return raw, None


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


def dedup_by_chip_id(records: list[tuple[str, dict]]) -> dict[str, dict]:
    """records: список (server_name, value). Повертає chip_id -> value з найновішим connect_time."""
    best: dict[str, dict] = {}
    for server_name, value in records:
        chip_id = value.get("chip_id")
        if not chip_id or chip_id == "unknown":
            continue
        value = {**value, "_server": server_name}
        prev = best.get(chip_id)
        if prev is None or (value.get("connect_time") or "") > (
            prev.get("connect_time") or ""
        ):
            best[chip_id] = value
    return best


async def _add_event(
    session, chip_id: str, event_type: str, details: dict | None = None
) -> None:
    session.add(
        DeviceEvent(
            chip_id=chip_id,
            type=event_type,
            details=json.dumps(details, ensure_ascii=False) if details else None,
        )
    )


async def _apply_snapshot(
    session, chip_id: str, value: dict, now: datetime.datetime
) -> None:
    firmware, firmware_id = _split_firmware(value.get("firmware"))
    server_name = value.get("_server")
    connect_time = value.get("connect_time")
    lat, lon = _parse_location(value.get("location"))

    device = await session.get(Device, chip_id)
    is_new = device is None
    was_offline = is_new or not device.is_online
    prev_firmware = None if is_new else device.firmware
    prev_location = None if is_new else device.location
    prev_connect = None if is_new else device.connect_time
    prev_ip = None if is_new else device.last_ip

    if is_new:
        device = Device(chip_id=chip_id, first_seen=now)
        session.add(device)

    device.firmware = firmware
    device.firmware_id = firmware_id
    device.hw_type = _hw_type(value) or device.hw_type
    device.is_online = True
    device.last_seen = now
    device.last_online_at = now
    device.connect_time = connect_time
    device.last_ip = value.get("ip") or device.last_ip
    device.city = value.get("city")
    device.region = value.get("region")
    device.country = value.get("country")
    device.timezone = value.get("timezone")
    device.org = value.get("org")
    device.location = value.get("location")
    device.lat, device.lon = lat, lon
    latency = value.get("latency")
    device.latency = latency if isinstance(latency, int) else device.latency
    sc = value.get("secure_connection")
    device.secure_connection = (
        (sc.lower() == "true")
        if isinstance(sc, str)
        else bool(sc) if sc is not None else None
    )
    device.last_server = server_name

    # Події
    if is_new:
        await _add_event(session, chip_id, "first_seen", {"firmware": firmware})
    if was_offline:
        await _add_event(session, chip_id, "online", {"server": server_name})
    if not is_new and prev_firmware and firmware and prev_firmware != firmware:
        await _add_event(
            session, chip_id, "firmware_change", {"from": prev_firmware, "to": firmware}
        )
    if (
        not is_new
        and prev_location
        and device.location
        and prev_location != device.location
    ):
        await _add_event(
            session,
            chip_id,
            "geo_change",
            {"from": prev_location, "to": device.location},
        )
    new_ip = value.get("ip")
    if not is_new and not was_offline and prev_ip and new_ip and prev_ip != new_ip:
        await _add_event(session, chip_id, "ip_change", {"from": prev_ip, "to": new_ip})

    # Сесія: нова, якщо пристрій був офлайн або змінився connect_time
    new_session_needed = was_offline or (connect_time and connect_time != prev_connect)
    if new_session_needed:
        await _close_open_sessions(session, chip_id, now)
        session.add(
            DeviceSession(
                chip_id=chip_id,
                server_name=server_name,
                connect_time=connect_time,
                started_at=now,
                firmware=firmware,
                firmware_id=firmware_id,
                ip=value.get("ip"),
                city=value.get("city"),
                region=value.get("region"),
            )
        )


async def _close_open_sessions(session, chip_id: str, now: datetime.datetime) -> None:
    result = await session.execute(
        select(DeviceSession).where(
            DeviceSession.chip_id == chip_id, DeviceSession.ended_at.is_(None)
        )
    )
    for s in result.scalars().all():
        s.ended_at = now
        started = s.started_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=datetime.timezone.utc)
        s.duration_sec = int((now - started).total_seconds()) if started else None


async def _mark_stale_offline(
    session, seen_chip_ids: set[str], now: datetime.datetime
) -> int:
    """Позначає офлайн ті пристрої, яких не бачили довше за поріг."""
    threshold = now - datetime.timedelta(seconds=OFFLINE_AFTER_SECONDS)
    result = await session.execute(
        select(Device).where(Device.is_online.is_(True), Device.last_seen < threshold)
    )
    count = 0
    for device in result.scalars().all():
        if device.chip_id in seen_chip_ids:
            continue
        device.is_online = False
        device.last_online_at = device.last_seen
        await _close_open_sessions(session, device.chip_id, device.last_seen or now)
        await _add_event(session, device.chip_id, "offline", None)
        count += 1
    return count


async def collect_once(servers: list[RedisServer]) -> dict:
    now = utcnow()
    scans = await asyncio.gather(
        *[scan_clients(s.client) for s in servers], return_exceptions=True
    )
    records: list[tuple[str, dict]] = []
    per_server: dict[str, int] = {}
    for server, result in zip(servers, scans):
        if isinstance(result, Exception):
            logger.error("Помилка скану Redis %s: %s", server.name, result)
            per_server[server.name] = -1
            continue
        per_server[server.name] = len(result)
        for value in result:
            records.append((server.name, value))

    deduped = dedup_by_chip_id(records)

    async with SessionLocal() as session:
        for chip_id, value in deduped.items():
            await _apply_snapshot(session, chip_id, value, now)
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
