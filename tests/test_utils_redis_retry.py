"""Звіряє retry-поведінку get_redis_data/set_redis_data з utils.py: одна транзиєнтна
redis.exceptions.ConnectionError/TimeoutError має мовчки перепробуватись (не губити дані і не
шуміти в логах), а стійка відмова - все ще логуватись і повертати default_response, як і
раніше. Народилось із живого інциденту: radiation_dev/ukrenergo_dev's власний heartbeat-запис
(service_is_fine -> set_redis_data) періодично ловив "Connection closed by server." від
пула з'єднань, застояного між рідкісними циклами (30 хв у radiation_dev), і оскільки нічого не
перепробовувало - Docker healthcheck бачив застарілий heartbeat і переходив у unhealthy."""

import logging

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from utils import get_redis_data, set_redis_data

logger = logging.getLogger("test")


class FlakyRedis:
    """Кидає RedisConnectionError на перші `fail_times` викликів будь-якого awaited методу,
    потім працює нормально - імітує пул, що віддав мертве з'єднання один раз."""

    def __init__(self, fail_times=1):
        self.fail_times = fail_times
        self.calls = 0
        self.store = {}

    def _maybe_fail(self):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RedisConnectionError("Connection closed by server.")

    async def type(self, key):
        self._maybe_fail()
        if key not in self.store:
            return "none"
        return "string"

    async def get(self, key):
        self._maybe_fail()
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self._maybe_fail()
        self.store[key] = value

    def pipeline(self):
        raise NotImplementedError("not used by the string-value cases this test exercises")


@pytest.mark.asyncio
async def test_set_redis_data_retries_once_on_transient_connection_error():
    client = FlakyRedis(fail_times=1)
    await set_redis_data(logger, client, "k", "hello")
    assert client.store["k"] == '"hello"'
    assert client.calls == 2  # 1 failed attempt + 1 successful retry


@pytest.mark.asyncio
async def test_set_redis_data_gives_up_after_second_consecutive_failure(caplog):
    client = FlakyRedis(fail_times=2)  # both the first attempt AND the single retry fail
    with caplog.at_level(logging.ERROR):
        await set_redis_data(logger, client, "k", "hello")
    assert "k" not in client.store
    assert client.calls == 2  # no second retry - the retry helper only retries once
    assert any("Error storing data in Redis" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_get_redis_data_retries_once_on_transient_connection_error():
    client = FlakyRedis(fail_times=1)
    client.store["k"] = '"hello"'
    result = await get_redis_data(logger, client, "k", default_response=None)
    assert result == "hello"
    # 1 failed `type` call, then a full retry of the whole fetch (`type` + `get` this time)
    assert client.calls == 3


@pytest.mark.asyncio
async def test_get_redis_data_returns_default_after_second_consecutive_failure(caplog):
    client = FlakyRedis(fail_times=2)
    with caplog.at_level(logging.ERROR):
        result = await get_redis_data(logger, client, "k", default_response="fallback")
    assert result == "fallback"
    assert client.calls == 2
