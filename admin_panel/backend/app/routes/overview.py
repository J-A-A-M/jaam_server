"""Дашборд: агреговані KPI, розподіли, тренд онлайну (з історії сесій)."""

import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import SERVER_TZ
from ..db import get_session
from ..deps import get_current_user
from ..models import Device, DeviceSession, JaamMap, utcnow
from ..schemas import CountItem, OverviewOut, TrendPoint

router = APIRouter(prefix="/api/overview", tags=["overview"])

BUCKET_MINUTES = 15
HISTORY_HOURS = 24
TREND_BUCKET_MINUTES = 30

_SERVER_ZONE = ZoneInfo(SERVER_TZ)


def _aware(dt: datetime.datetime | None) -> datetime.datetime | None:
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def _connect_time_to_utc(raw: str | None) -> datetime.datetime | None:
    """connect_time пишеться websocket_server у локальному часі сервера (без TZ)."""
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            naive = datetime.datetime.strptime(raw, fmt)
            tz = datetime.timezone.utc if raw.endswith("Z") else _SERVER_ZONE
            return naive.replace(tzinfo=tz).astimezone(datetime.timezone.utc)
        except ValueError:
            continue
    return None


def _duration_label(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    if h == 0:
        return f"{m}хв"
    if m == 0:
        return f"{h}г"
    return f"{h}г {m}хв"


def _median_label(durations_min: list[float]) -> str:
    if not durations_min:
        return "—"
    s = sorted(durations_min)
    n = len(s)
    mid = n // 2
    median = s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2
    return _duration_label(median)


async def _grouped(session: AsyncSession, column, limit: int = 12) -> list[CountItem]:
    result = await session.execute(
        select(column, func.count())
        .where(column.is_not(None))
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    )
    return [CountItem(label=str(label), count=count) for label, count in result.all()]


@router.get("", response_model=OverviewOut)
async def overview(
    user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    now = utcnow()
    day_ago = now - datetime.timedelta(hours=24)

    online_now = await session.scalar(select(func.count()).select_from(Device).where(Device.is_online.is_(True)))
    total_registered = await session.scalar(select(func.count()).select_from(Device))
    registry_total = await session.scalar(select(func.count()).select_from(JaamMap))
    jaam_online = await session.scalar(
        select(func.count())
        .select_from(Device)
        .where(Device.is_online.is_(True), Device.chip_id.in_(select(JaamMap.chip_id)))
    )
    self_online = (online_now or 0) - (jaam_online or 0)
    unique_24h = await session.scalar(select(func.count()).select_from(Device).where(Device.last_seen >= day_ago))
    new_24h = await session.scalar(select(func.count()).select_from(Device).where(Device.first_seen >= day_ago))

    # Тривалості поточного онлайну — з connect_time мап (реальна тривалість, як у maps_online)
    online_rows = await session.execute(select(Device.connect_time).where(Device.is_online.is_(True)))
    durations_min = []
    for (raw,) in online_rows.all():
        ct = _connect_time_to_utc(raw)
        if ct is not None:
            durations_min.append(max(0.0, (now - ct).total_seconds() / 60))

    # Гістограма тривалості онлайну (15-хв бакети, макс 24 год)
    total_buckets = (HISTORY_HOURS * 60) // BUCKET_MINUTES
    hist = [0] * total_buckets
    older = 0
    for d in durations_min:
        if d >= HISTORY_HOURS * 60:
            older += 1
        else:
            hist[int(d // BUCKET_MINUTES)] += 1
    hist_labels = [_duration_label((i + 1) * BUCKET_MINUTES) for i in range(total_buckets)]
    if older:
        hist_labels[-1] = f">{HISTORY_HOURS}г"
        hist[-1] += older
    duration_histogram = [CountItem(label=l, count=c) for l, c in zip(hist_labels, hist)]

    # Тренд онлайну за 24 год з історії сесій (сесія активна в момент t, якщо started<=t<ended|now)
    sess_res = await session.execute(
        select(DeviceSession.started_at, DeviceSession.ended_at).where(
            (DeviceSession.ended_at.is_(None)) | (DeviceSession.ended_at >= day_ago)
        )
    )
    sessions = [(_aware(s), _aware(e)) for s, e in sess_res.all()]
    trend: list[TrendPoint] = []
    steps = (HISTORY_HOURS * 60) // TREND_BUCKET_MINUTES
    for i in range(steps + 1):
        t = day_ago + datetime.timedelta(minutes=i * TREND_BUCKET_MINUTES)
        count = sum(1 for s, e in sessions if s and s <= t and (e is None or e >= t))
        trend.append(TrendPoint(ts=t, online=count))

    return OverviewOut(
        online_now=online_now or 0,
        jaam_online=jaam_online or 0,
        self_online=self_online,
        registry_total=registry_total or 0,
        total_registered=total_registered or 0,
        unique_24h=unique_24h or 0,
        new_24h=new_24h or 0,
        median_online=_median_label(durations_min),
        by_firmware=await _grouped(session, Device.firmware),
        by_hw=await _grouped(session, Device.hw_type),
        by_region=await _grouped(session, Device.region),
        by_country=await _grouped(session, Device.country),
        duration_histogram=duration_histogram,
        online_trend=trend,
    )
