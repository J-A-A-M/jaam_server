FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY websocket_server/websocket_server.py .
COPY websocket_server/GeoLite2-City.mmdb .
COPY utils.py .
COPY regions.json .
RUN --mount=type=bind,source=websocket_server/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
# python:3.13-slim has no curl - process_request() answers plain HTTP GET /healthz before the
# WS upgrade (websockets lib), so a plain urllib request works fine without pulling in curl.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://localhost:{os.environ.get(\"WEBSOCKET_PORT\",38440)}/healthz', timeout=3).status==200 else 1)"
CMD ["python", "websocket_server.py"]