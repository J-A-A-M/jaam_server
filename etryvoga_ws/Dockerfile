FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY etryvoga_ws/etryvoga_ws.py .
COPY utils.py .
COPY regions.json .
COPY healthcheck_redis_heartbeat.py .
RUN --mount=type=bind,source=etryvoga_ws/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV HEARTBEAT_KEY="alerts:etryvoga_ws:last_call"
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck_redis_heartbeat.py
CMD ["python", "etryvoga_ws.py"]
