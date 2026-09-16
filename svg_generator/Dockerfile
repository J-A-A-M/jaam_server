FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY svg_generator/svg_generator.py .
COPY utils.py .
COPY regions.json .
COPY healthcheck_redis_heartbeat.py .
RUN --mount=type=bind,source=svg_generator/requirements.txt,target=/tmp/requirements.txt \
    apt-get update && apt-get install --no-install-recommends -y libcairo2 && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV HEARTBEAT_KEY="svg_generator:alerts:last_call"
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck_redis_heartbeat.py
CMD ["python", "svg_generator.py"]