#!/bin/bash

# Адмін-панель JAAM (FastAPI + React), моніторинг мап з агрегацією по кількох Redis

# --- Значення за замовчуванням ---
PORT=8099
REDIS_HOSTS=""                       # JSON-масив [{host,port,password,db,name}] для кількох серверів
REDIS_HOST="redis"
REDIS_PASSWORD="redis"
REDIS_DB="0"
DATABASE_URL="postgresql+asyncpg://jaam:jaam@postgres:5432/jaam_admin"
JWT_SECRET="change-me-in-production"
ADMIN_USER="admin"
ADMIN_PASSWORD="jaam_rocks"
COLLECT_INTERVAL="20"
COOKIE_SECURE="false"
LOGGING="INFO"
APP_ORIGIN="https://admin.jaam.net.ua"
RP_ID="admin.jaam.net.ua"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port) PORT="$2"; shift 2;;
        -rh|--redis-hosts) REDIS_HOSTS="$2"; shift 2;;
        -m|--redis-host) REDIS_HOST="$2"; shift 2;;
        -pw|--redis-password) REDIS_PASSWORD="$2"; shift 2;;
        -db|--redis-db) REDIS_DB="$2"; shift 2;;
        -d|--database-url) DATABASE_URL="$2"; shift 2;;
        -s|--jwt-secret) JWT_SECRET="$2"; shift 2;;
        -au|--admin-user) ADMIN_USER="$2"; shift 2;;
        -ap|--admin-password) ADMIN_PASSWORD="$2"; shift 2;;
        -ci|--collect-interval) COLLECT_INTERVAL="$2"; shift 2;;
        -cs|--cookie-secure) COOKIE_SECURE="$2"; shift 2;;
        -l|--logging) LOGGING="$2"; shift 2;;
        --app-origin) APP_ORIGIN="$2"; shift 2;;
        --rp-id) RP_ID="$2"; shift 2;;
        *) echo "Unknown argument: $1"; exit 1;;
    esac
done

echo "ADMIN_PANEL"
echo "PORT: $PORT"
echo "REDIS_HOSTS: $REDIS_HOSTS"
echo "REDIS_HOST: $REDIS_HOST"
echo "DATABASE_URL: $DATABASE_URL"
echo "ADMIN_USER: $ADMIN_USER"
echo "COLLECT_INTERVAL: $COLLECT_INTERVAL"
echo "LOGGING: $LOGGING"

echo "Updating Git repo..."
git pull

echo "Building Docker image..."
docker build -t jaam_admin_panel -f admin_panel/Dockerfile admin_panel

echo "Stopping and removing old container..."
docker stop jaam_admin_panel || true
docker rm jaam_admin_panel || true

echo "Deploying new container..."
docker run --name jaam_admin_panel \
    --restart unless-stopped \
    --network=jaam \
    -d \
    -p "$PORT":8099 \
    --env PORT="8099" \
    --env REDIS_HOSTS="$REDIS_HOSTS" \
    --env REDIS_HOST="$REDIS_HOST" \
    --env REDIS_PASSWORD="$REDIS_PASSWORD" \
    --env REDIS_DB="$REDIS_DB" \
    --env DATABASE_URL="$DATABASE_URL" \
    --env JWT_SECRET="$JWT_SECRET" \
    --env ADMIN_USER="$ADMIN_USER" \
    --env ADMIN_PASSWORD="$ADMIN_PASSWORD" \
    --env COLLECT_INTERVAL="$COLLECT_INTERVAL" \
    --env COOKIE_SECURE="$COOKIE_SECURE" \
    --env LOGGING="$LOGGING" \
    --env APP_ORIGIN="$APP_ORIGIN" \
    --env RP_ID="$RP_ID" \
    jaam_admin_panel

echo "Container deployed successfully!"
