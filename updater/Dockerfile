FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY updater/updater.py .
COPY updater/pubsub_loop.py .
COPY updater/files.py .
COPY updater/processing ./processing
COPY utils.py .
COPY regions.json .
COPY healthcheck_redis_heartbeat.py .
RUN --mount=type=bind,source=updater/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV HEARTBEAT_KEY="updater:heartbeat:last_call"
ENV MAX_AGE_SECONDS=45
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck_redis_heartbeat.py
CMD ["python", "updater.py"]