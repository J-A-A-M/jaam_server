FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY update_server/update_server.py .
COPY utils.py .
COPY regions.json .
RUN --mount=type=bind,source=update_server/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,sys,urllib.request; sys.exit(0 if urllib.request.urlopen(f'http://localhost:{os.environ.get(\"PORT\",8090)}/healthz', timeout=3).status==200 else 1)"
CMD ["python", "update_server.py"]