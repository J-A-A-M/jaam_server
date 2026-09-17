"""Періодичне прибирання старої історії, щоб таблиці не розпухали.

Видаляємо завершені device_sessions і РУТИННІ події (online/offline/ip_change),
старші за поріг. Події життєвого циклу мапи — поява (first_seen), зміна прошивки
(firmware_change/firmware_id_change) та зміна локації (geo_change) — мають імунітет
і не видаляються ніколи.

Видалення виконується батчами, щоб не тримати довгий лок на великій таблиці,
і запускається раз на добу окремим фоновим завданням.
"""

import asyncio
import datetime
import logging

from sqlalchemy import bindparam, text

from .config import EVENTS_RETENTION_DAYS, SESSIONS_RETENTION_DAYS
from .db import SessionLocal
from .models import utcnow

logger = logging.getLogger("admin_panel.retention")

RETENTION_INTERVAL_SECONDS = 24 * 3600
_BATCH = 5000

# Події, які НІКОЛИ не видаляються (історія життєвого циклу мапи).
IMMUNE_EVENT_TYPES = ("first_seen", "firmware_change", "firmware_id_change", "geo_change")

_DELETE_EVENTS = text("""
    DELETE FROM device_events
    WHERE id IN (
        SELECT id FROM device_events
        WHERE ts < :cutoff AND type NOT IN :immune
        LIMIT :batch
    )
    """).bindparams(bindparam("immune", expanding=True))

_DELETE_SESSIONS = text("""
    DELETE FROM device_sessions
    WHERE id IN (
        SELECT id FROM device_sessions
        WHERE ended_at IS NOT NULL AND ended_at < :cutoff
        LIMIT :batch
    )
    """)


async def _purge(stmt, params: dict) -> int:
    """Видаляє рядки батчами доти, доки є що видаляти. Повертає загальну кількість."""
    total = 0
    while True:
        async with SessionLocal() as session:
            result = await session.execute(stmt, params)
            await session.commit()
        deleted = result.rowcount or 0
        total += deleted
        if deleted < _BATCH:
            break
    return total


async def run_retention_once() -> dict:
    now = utcnow()
    stats: dict = {}
    if EVENTS_RETENTION_DAYS > 0:
        cutoff = now - datetime.timedelta(days=EVENTS_RETENTION_DAYS)
        stats["events_deleted"] = await _purge(
            _DELETE_EVENTS,
            {"cutoff": cutoff, "immune": list(IMMUNE_EVENT_TYPES), "batch": _BATCH},
        )
    if SESSIONS_RETENTION_DAYS > 0:
        cutoff = now - datetime.timedelta(days=SESSIONS_RETENTION_DAYS)
        stats["sessions_deleted"] = await _purge(
            _DELETE_SESSIONS,
            {"cutoff": cutoff, "batch": _BATCH},
        )
    if stats:
        logger.info("Retention: %s", stats)
    return stats


async def run_retention(stop_event: asyncio.Event) -> None:
    if EVENTS_RETENTION_DAYS <= 0 and SESSIONS_RETENTION_DAYS <= 0:
        logger.info("Retention вимкнено (обидва пороги 0)")
        return
    logger.info(
        "Retention-loop стартував (події %sд, сесії %sд, раз на %sг)",
        EVENTS_RETENTION_DAYS,
        SESSIONS_RETENTION_DAYS,
        RETENTION_INTERVAL_SECONDS // 3600,
    )
    while not stop_event.is_set():
        try:
            await run_retention_once()
        except Exception:
            logger.exception("Помилка в циклі retention")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=RETENTION_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            pass
