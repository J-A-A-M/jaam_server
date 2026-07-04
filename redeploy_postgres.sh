#!/bin/bash

# Postgres для адмін-панелі (реєстр мап + історія)

POSTGRES_PORT=5432
POSTGRES_USER="jaam"
POSTGRES_PASSWORD="jaam"
POSTGRES_DB="jaam_admin"
POSTGRES_DATA_PATH="/shared_data/postgres"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port) POSTGRES_PORT="$2"; shift 2;;
        -u|--user) POSTGRES_USER="$2"; shift 2;;
        -w|--password) POSTGRES_PASSWORD="$2"; shift 2;;
        -db|--database) POSTGRES_DB="$2"; shift 2;;
        -d|--data-path) POSTGRES_DATA_PATH="$2"; shift 2;;
        *) echo "Unknown argument: $1"; exit 1;;
    esac
done

echo "POSTGRES"
echo "POSTGRES_PORT: $POSTGRES_PORT"
echo "POSTGRES_USER: $POSTGRES_USER"
echo "POSTGRES_PASSWORD: ******"
echo "POSTGRES_DB: $POSTGRES_DB"
echo "POSTGRES_DATA_PATH: $POSTGRES_DATA_PATH"

echo "Creating data directory..."
mkdir -p "$POSTGRES_DATA_PATH"

# Graceful stop of old container
if docker ps -q -f name=postgres | grep -q .; then
    echo "Stopping old Postgres container..."
    docker stop -t 10 postgres || true
fi
docker rm postgres || true

echo "Deploying Postgres container..."
docker run --name postgres \
    --restart unless-stopped \
    --network=jaam -d \
    -p "$POSTGRES_PORT":5432 \
    -v "$POSTGRES_DATA_PATH":/var/lib/postgresql/data \
    --env POSTGRES_USER="$POSTGRES_USER" \
    --env POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    --env POSTGRES_DB="$POSTGRES_DB" \
    postgres:16-alpine

echo "Container deployed successfully!"
