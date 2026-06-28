#!/bin/bash

# Default values
PORT=8090
MASTER_KEY=""
SESSION_SECRET=""
LOGGING="INFO"
DATABASE_URL=""
NP_API_KEY=""
# Параметри відправника Нова Пошта (не секретні; підставити свої).
NP_SENDER_REF=""
NP_SENDER_CONTACT_REF=""
NP_SENDER_PHONE=""
NP_SENDER_CITY_REF=""
NP_SENDER_ADDRESS_REF=""

# Check for arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -mk|--master-key)
            MASTER_KEY="$2"
            shift 2
            ;;
        -ss|--session-secret)
            SESSION_SECRET="$2"
            shift 2
            ;;
        -l|--logging)
            LOGGING="$2"
            shift 2
            ;;
        -db|--database-url)
            DATABASE_URL="$2"
            shift 2
            ;;
        -np|--np-api-key)
            NP_API_KEY="$2"
            shift 2
            ;;
        --np-sender-ref)
            NP_SENDER_REF="$2"; shift 2 ;;
        --np-sender-contact-ref)
            NP_SENDER_CONTACT_REF="$2"; shift 2 ;;
        --np-sender-phone)
            NP_SENDER_PHONE="$2"; shift 2 ;;
        --np-sender-city-ref)
            NP_SENDER_CITY_REF="$2"; shift 2 ;;
        --np-sender-address-ref)
            NP_SENDER_ADDRESS_REF="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

echo "STORE"

echo "PORT: $PORT"
echo "MASTER_KEY: ***"
echo "SESSION_SECRET: ***"
echo "LOGGING: $LOGGING"
if [ -n "$DATABASE_URL" ]; then
    echo "DATABASE_URL: ***"
else
    echo "DATABASE_URL: (not set, using SQLite)"
fi

# Updating the Git repo
echo "Updating Git repo..."
git pull

# Building Docker image
echo "Building Docker image..."
docker build -t map_store -f store/Dockerfile .

mkdir -p "store_data"

# Stopping and removing the old container (if exists)
echo "Stopping and removing old container..."
docker stop map_store || true
docker rm map_store || true

# Deploying the new container
echo "Deploying new container..."
docker run --name map_store \
    --restart unless-stopped \
    --network=jaam \
    -d \
    -p "$PORT":8090 \
    -v /store_data:/data \
    --env PORT=8090 \
    --env HOST=0.0.0.0 \
    --env MASTER_KEY="$MASTER_KEY" \
    --env SESSION_SECRET="$SESSION_SECRET" \
    --env LOGGING="$LOGGING" \
    --env NP_API_KEY="$NP_API_KEY" \
    --env NP_SENDER_REF="$NP_SENDER_REF" \
    --env NP_SENDER_CONTACT_REF="$NP_SENDER_CONTACT_REF" \
    --env NP_SENDER_PHONE="$NP_SENDER_PHONE" \
    --env NP_SENDER_CITY_REF="$NP_SENDER_CITY_REF" \
    --env NP_SENDER_ADDRESS_REF="$NP_SENDER_ADDRESS_REF" \
    --env NP_DEFAULT_WEIGHT="${NP_DEFAULT_WEIGHT:-0.5}" \
    --env NP_SEAT_WIDTH="${NP_SEAT_WIDTH:-20}" \
    --env NP_SEAT_LENGTH="${NP_SEAT_LENGTH:-20}" \
    --env NP_SEAT_HEIGHT="${NP_SEAT_HEIGHT:-20}" \
    $([ -n "$DATABASE_URL" ] && echo "--env DATABASE_URL=\"$DATABASE_URL\"") \
    map_store

echo "Container deployed successfully!"
