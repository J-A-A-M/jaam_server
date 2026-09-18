"""Docker HEALTHCHECK: контейнер здоровий, поки connect_neptun_ws регулярно
оновлює heartbeat alerts:neptun_ws:last_call (пишеться на кожен вхідний
фрейм, включно з heartbeat-фреймами від neptun кожні ~15с). Синхронний
клієнт — процес короткоживучий, окремий event loop тут не потрібен.
"""

import datetime
import json
import os
import sys

import redis

redis_host = os.environ.get("REDIS_HOST") or "redis"
redis_port = int(os.environ.get("REDIS_PORT", 6379))
redis_password = os.environ.get("REDIS_PASSWORD") or "redis"
redis_db = int(os.environ.get("REDIS_DB", 0))

LAST_CALL_KEY = "alerts:neptun_ws:last_call"
# neptun шле heartbeat-фрейм кожні ~15с — 60с з запасом на мережеву гикавку.
MAX_AGE_SECONDS = 600


def main():
    try:
        client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        raw = client.get(LAST_CALL_KEY)
    except redis.RedisError as e:
        print(f"unhealthy: redis error: {e}")
        return 1

    if not raw:
        print("unhealthy: heartbeat ще не з'явився")
        return 1

    last_call = datetime.datetime.strptime(json.loads(raw), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - last_call).total_seconds()
    if age > MAX_AGE_SECONDS:
        print(f"unhealthy: heartbeat застарів ({age:.0f}s > {MAX_AGE_SECONDS:.0f}s)")
        return 1

    print(f"healthy: heartbeat {age:.0f}s тому")
    return 0


if __name__ == "__main__":
    sys.exit(main())
