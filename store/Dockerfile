FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
WORKDIR /srv
COPY store/app /srv/app
COPY store/data /srv/data
RUN --mount=type=bind,source=store/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
ENV STORE_DB_PATH=/data/store.db
ENV UPLOAD_DIR=/data/uploads
CMD ["python", "-m", "app.main"]
