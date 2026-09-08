FROM python:3.13-slim
ENV TZ="Europe/Kyiv"
COPY respublika_alert_notifier/respublika_alert_notifier.py .
COPY respublika_alert_notifier/logic.py .
COPY utils.py .
RUN --mount=type=bind,source=respublika_alert_notifier/requirements.txt,target=/tmp/requirements.txt \
    python -m pip install --no-cache-dir -r /tmp/requirements.txt
CMD ["python", "respublika_alert_notifier.py"]
