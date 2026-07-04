"""Pydantic-схеми відповідей API."""

import datetime

from pydantic import BaseModel, ConfigDict


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    username: str
    role: str


class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "admin"


class UserListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    created_at: datetime.datetime


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chip_id: str
    firmware: str | None
    firmware_id: str | None
    hw_type: str | None
    is_online: bool
    first_seen: datetime.datetime
    last_seen: datetime.datetime
    last_online_at: datetime.datetime | None
    connect_time: str | None
    last_ip: str | None
    city: str | None
    region: str | None
    country: str | None
    org: str | None
    location: str | None
    lat: float | None
    lon: float | None
    latency: int | None
    secure_connection: bool | None
    last_server: str | None

    # Склейка з реєстром JAAM (заповнюється, якщо chip_id є в sold_maps)
    is_jaam: bool = False
    hw_version: str | None = None
    is_prototype: bool | None = None
    order_number: str | None = None
    customer_info: str | None = None


class DeviceListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[DeviceOut]


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    server_name: str | None
    connect_time: str | None
    started_at: datetime.datetime
    ended_at: datetime.datetime | None
    duration_sec: int | None
    firmware: str | None
    firmware_id: str | None = None
    ip: str | None
    city: str | None
    region: str | None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    ts: datetime.datetime
    details: str | None


class DeviceDetailOut(BaseModel):
    device: DeviceOut
    sessions: list[SessionOut]
    events: list[EventOut]


class CountItem(BaseModel):
    label: str
    count: int


class TrendPoint(BaseModel):
    ts: datetime.datetime
    online: int


class JaamMapIn(BaseModel):
    chip_id: str
    hw_version: str | None = None
    is_prototype: bool = False
    order_number: str | None = None
    customer_info: str | None = None


class JaamMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chip_id: str
    hw_version: str | None
    is_prototype: bool
    order_number: str | None
    customer_info: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
    # Склейка зі станом онлайн
    ever_seen: bool = False
    is_online: bool = False
    last_seen: datetime.datetime | None = None
    firmware: str | None = None


class JaamMapListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[JaamMapOut]


class BulkResult(BaseModel):
    created: int
    updated: int
    total: int


class OverviewOut(BaseModel):
    online_now: int
    jaam_online: int
    self_online: int
    registry_total: int
    total_registered: int
    unique_24h: int
    new_24h: int
    median_online: str
    by_firmware: list[CountItem]
    by_hw: list[CountItem]
    by_region: list[CountItem]
    by_country: list[CountItem]
    by_city: list[CountItem]
    duration_histogram: list[CountItem]
    online_trend: list[TrendPoint]


class GeoPoint(BaseModel):
    chip_id: str
    lat: float
    lon: float
    is_online: bool
    firmware: str | None
    city: str | None
    region: str | None
    org: str | None
    last_seen: datetime.datetime


class ServerStatus(BaseModel):
    name: str
    ok: bool
    online: int
    checked_at: datetime.datetime
