"""Generic Docker HEALTHCHECK for services that write a heartbeat via utils.py's
service_is_fine(). Parametrized version of respublika_alert_notifier/healthcheck.py -
same logic, but the heartbeat key and staleness window come from env instead of being
hardcoded per-service, so one script covers every service in this pattern.

Required env: HEARTBEAT_KEY (the redis key service_is_fine() writes to).
Optional env: MAX_AGE_SECONDS (default 60), POLL_PERIOD (if set, MAX_AGE_SECONDS
defaults to max(POLL_PERIOD*10, 30) instead of the flat 60s default - mirrors the
respublika_alert_notifier original for services with a known short poll interval).
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

HEARTBEAT_KEY = os.environ.get("HEARTBEAT_KEY")

if os.environ.get("MAX_AGE_SECONDS"):
    MAX_AGE_SECONDS = float(os.environ["MAX_AGE_SECONDS"])
elif os.environ.get("POLL_PERIOD"):
    MAX_AGE_SECONDS = max(float(os.environ["POLL_PERIOD"]) * 10, 30)
else:
    MAX_AGE_SECONDS = 60


def main():
    if not HEARTBEAT_KEY:
        print("unhealthy: HEARTBEAT_KEY env not set")
        return 1

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
        raw = client.get(HEARTBEAT_KEY)
    except redis.RedisError as e:
        print(f"unhealthy: redis error: {e}")
        return 1

    if not raw:
        print(f"unhealthy: heartbeat {HEARTBEAT_KEY} ще не з'явився")
        return 1

    last_call = datetime.datetime.strptime(json.loads(raw), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    age = (datetime.datetime.now(datetime.timezone.utc) - last_call).total_seconds()
    if age > MAX_AGE_SECONDS:
        print(f"unhealthy: heartbeat {HEARTBEAT_KEY} застарів ({age:.0f}s > {MAX_AGE_SECONDS:.0f}s)")
        return 1

    print(f"healthy: heartbeat {HEARTBEAT_KEY} {age:.0f}s тому")
    return 0


if __name__ == "__main__":
    sys.exit(main())
