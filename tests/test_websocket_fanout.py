import asyncio
import os

import pytest

# geo = database.Reader(...) виконується при імпорті модуля
os.environ.setdefault(
    "GEO_PATH", os.path.join(os.path.dirname(__file__), "..", "websocket_server", "GeoLite2-City.mmdb")
)

from websocket_server.websocket_server import (  # noqa: E402
    ALL_CHANNELS,
    AlertVersion,
    FUSION_CHANNELS,
    LEGACY_VERSION_CHANNELS,
    SharedData,
    WEATHER_DATA_KEY,
    WEATHER_UPDATED_CHANNEL,
    channel_source,
    legacy_channels,
    redis_fanout,
)


def test_channel_source_matches_legacy_redis_keys():
    """
    channel_source() виводить redis_key як channel.removesuffix(":updated").
    LEGACY_VERSION_CHANNELS зберігає той самий ключ явно — вони мусять збігатися,
    інакше fan-out тихо читатиме не той ключ.
    """
    for version_channels in LEGACY_VERSION_CHANNELS.values():
        for channel, (redis_key, *_) in version_channels.items():
            assert channel_source(channel) == (redis_key, []), channel


def test_channel_source_fusion_overrides():
    assert channel_source("websocket:v1:fusion:alerts:updated") == ("websocket:v1:fusion:payload:alerts", "")
    assert channel_source("websocket:v1:fusion:etryvoga:updated") == (
        "websocket:v1:fusion:payload:notifications",
        "",
    )
    assert channel_source(WEATHER_UPDATED_CHANNEL) == (WEATHER_DATA_KEY, {})
    assert channel_source("websocket:v1:fusion:energy:updated") == ("websocket:v1:fusion:energy:data", {})
    assert channel_source("releases:beta:updated") == ("releases:beta", [])


def test_all_channels_cover_every_subscriber():
    """Спільний listener підписаний лише на ALL_CHANNELS — там має бути все, на що підписуються клієнти."""
    for version in (AlertVersion.v1, AlertVersion.v2, AlertVersion.v3, AlertVersion.v4):
        for channel in legacy_channels(version):
            assert channel in ALL_CHANNELS, channel
    for channel in FUSION_CHANNELS:
        assert channel in ALL_CHANNELS, channel


def test_subscribe_unsubscribe():
    shared = SharedData()
    queue = asyncio.Queue()
    shared.subscribe(queue, ["a", "b"])
    assert shared.subscribers["a"] == {queue}
    shared.unsubscribe(queue, ["a", "b"])
    assert shared.subscribers["a"] == set()
    shared.unsubscribe(queue, ["never-subscribed"])  # не має падати


@pytest.mark.asyncio
async def test_fanout_reads_once_and_drops_oldest(monkeypatch):
    """Одне читання Redis на подію незалежно від кількості підписників; повний queue втрачає найстаріше."""
    channel = "releases:beta:updated"
    reads = []

    async def fake_get_redis_data(log, client, key, default_response=None):
        reads.append(key)
        return [{"tag": f"5.0.{len(reads)}"}]

    monkeypatch.setattr("websocket_server.websocket_server.get_redis_data", fake_get_redis_data)

    shared = SharedData()
    queues = [asyncio.Queue(maxsize=1) for _ in range(3)]
    for queue in queues:
        shared.subscribe(queue, [channel])

    # None — це звичайний 1-секундний timeout tick, найчастіший шлях у проді
    messages = [None, {"type": "message", "channel": channel}, None, {"type": "message", "channel": channel}]

    class FakePubSub:
        async def subscribe(self, *channels):
            pass

        async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            if messages:
                return messages.pop(0)
            raise asyncio.CancelledError

        async def aclose(self):
            pass

    class FakeRedis:
        def pubsub(self):
            return FakePubSub()

    shared.redis_client = FakeRedis()

    with pytest.raises(asyncio.CancelledError):
        await redis_fanout(shared)

    # два повідомлення -> рівно два читання, а не два на кожного з трьох підписників
    assert reads == ["releases:beta", "releases:beta"]
    for queue in queues:
        assert queue.qsize() == 1
        _, data = queue.get_nowait()
        assert data == [{"tag": "5.0.2"}]  # drop-oldest лишив найновіше
