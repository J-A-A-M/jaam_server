FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY maps_online/maps_online.py .
RUN --mount=type=bind,source=maps_online/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
CMD ["python", "maps_online.py"]
