"""Docker HEALTHCHECK: контейнер здоровий, поки notify_on_change регулярно
оновлює heartbeat respublika_alert_notifier:last_call (пишеться щотіку через
service_is_fine). Синхронний клієнт — процес короткоживучий, окремий event
loop тут не потрібен.
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
poll_period = float(os.environ.get("POLL_PERIOD", 1))

LAST_CALL_KEY = "respublika_alert_notifier:last_call"
# Скільки тіків можна пропустити (мережевий гикавка, повільний GC) перш ніж
# вважати контейнер нездоровим.
MAX_AGE_SECONDS = max(poll_period * 10, 30)


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
