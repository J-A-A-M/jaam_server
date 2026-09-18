FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY neptun_ws/neptun_ws.py .
COPY neptun_ws/healthcheck.py .
COPY utils.py .
COPY regions.json .
COPY raions.geojson .
COPY oblasts.geojson .
RUN --mount=type=bind,source=neptun_ws/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python healthcheck.py
CMD ["python", "neptun_ws.py"]
