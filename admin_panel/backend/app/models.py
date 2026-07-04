"""Моделі БД: реєстр пристроїв за chip_id, історія сесій, події, користувачі."""

import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class Device(Base):
    """Один рядок на унікальну мапу (ключ — стабільний chip_id)."""

    __tablename__ = "devices"

    chip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    firmware: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    firmware_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    hw_type: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)

    is_online: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    first_seen: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_online_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    connect_time: Mapped[str | None] = mapped_column(String(32), nullable=True)

    last_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    org: Mapped[str | None] = mapped_column(String(256), nullable=True)
    location: Mapped[str | None] = mapped_column(String(64), nullable=True)  # "lat,lon"
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)

    latency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    secure_connection: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_server: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    sessions: Mapped[list["DeviceSession"]] = relationship(back_populates="device", cascade="all, delete-orphan")
    events: Mapped[list["DeviceEvent"]] = relationship(back_populates="device", cascade="all, delete-orphan")


class DeviceSession(Base):
    """Одна сесія онлайну мапи (від connect_time до зникнення з Redis)."""

    __tablename__ = "device_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chip_id: Mapped[str] = mapped_column(ForeignKey("devices.chip_id", ondelete="CASCADE"), index=True)
    server_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    connect_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    ended_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    firmware: Mapped[str | None] = mapped_column(String(64), nullable=True)
    firmware_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)

    device: Mapped[Device] = relationship(back_populates="sessions")


class DeviceEvent(Base):
    """Значуща подія: online / offline / firmware_change / geo_change."""

    __tablename__ = "device_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chip_id: Mapped[str] = mapped_column(ForeignKey("devices.chip_id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON-рядок

    device: Mapped[Device] = relationship(back_populates="events")


class JaamMap(Base):
    """Реєстр офіційних JAAM-мап (з Google-таблиці продажів).

    Ключ — chip_id, збігається з Device.chip_id для склейки з онлайн-станом.
    Самозбірки сюди не потрапляють (є лише в devices, якщо були онлайн).
    """

    __tablename__ = "jaam_maps"

    chip_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    hw_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_prototype: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    order_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    customer_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class User(Base):
    """Користувач адмін-панелі."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="admin")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
