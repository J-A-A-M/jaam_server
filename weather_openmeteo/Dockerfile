FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY weather_openmeteo/weather_openmeteo.py .
COPY utils.py .
COPY regions.json .
COPY healthcheck_redis_heartbeat.py .
RUN --mount=type=bind,source=weather_openmeteo/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV HEARTBEAT_KEY="weather:openmeteo:last_call"
# OPENMETEO_PERIOD defaults to 3600s (one fetch/hour) - the 60s flat default would flag this
# service unhealthy for most of every hour.
ENV MAX_AGE_SECONDS=3700
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck_redis_heartbeat.py
CMD ["python", "weather_openmeteo.py"]
