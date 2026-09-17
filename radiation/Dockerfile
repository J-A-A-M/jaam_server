FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY radiation/radiation.py .
COPY utils.py .
COPY regions.json .
COPY healthcheck_redis_heartbeat.py .
RUN --mount=type=bind,source=radiation/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV HEARTBEAT_KEY="radiation:saveecobot:data:last_call"
# SAVEECOBOT_DATA_UPDATE_PERIOD defaults to 1800s - the 60s flat default would flag this
# service unhealthy for most of every cycle.
ENV MAX_AGE_SECONDS=1900
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck_redis_heartbeat.py
CMD ["python", "radiation.py"]