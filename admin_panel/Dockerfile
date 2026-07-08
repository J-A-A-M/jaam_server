# --- Stage 1: збірка React SPA ---
FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Stage 2: backend + статика ---
FROM python:3.13-slim
ENV TZ="Europe/Kyiv" \
    PYTHONUNBUFFERED=1 \
    STATIC_DIR=/app/static
WORKDIR /app

COPY backend/requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend /frontend/dist ./static

EXPOSE 8099
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8099", "--proxy-headers", "--forwarded-allow-ips", "*"]
