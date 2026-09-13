#!/bin/bash

# Default values
REDIS_HOST=""
REDIS_PASSWORD="redis"
REDIS_DB="0"
RESPUBLIKA_ALERTS_WEBHOOK_URL=""
POLL_PERIOD=1
TEST_MODE="false"
LOGGING="INFO"

# Check for arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -m|--redis-host)
            REDIS_HOST="$2"
            shift 2
            ;;
        -pw|--redis-password)
            REDIS_PASSWORD="$2"
            shift 2
            ;;
        -db|--redis-db)
            REDIS_DB="$2"
            shift 2
            ;;
        -u|--webhook-url)
            RESPUBLIKA_ALERTS_WEBHOOK_URL="$2"
            shift 2
            ;;
        -p|--poll-period)
            POLL_PERIOD="$2"
            shift 2
            ;;
        -t|--test-mode)
            TEST_MODE="$2"
            shift 2
            ;;
        -l|--logging)
            LOGGING="$2"
            shift 2
            ;;
        *)
            echo "Unknown argument: $1"
            exit 1
            ;;
    esac
done

echo "RESPUBLIKA ALERT NOTIFIER"

echo "REDIS_HOST: $REDIS_HOST"
echo "REDIS_PASSWORD: $REDIS_PASSWORD"
echo "REDIS_DB: $REDIS_DB"
echo "RESPUBLIKA_ALERTS_WEBHOOK_URL: $RESPUBLIKA_ALERTS_WEBHOOK_URL"
echo "POLL_PERIOD: $POLL_PERIOD"
echo "TEST_MODE: $TEST_MODE"
echo "LOGGING: $LOGGING"


# Updating the Git repo
echo "Updating Git repo..."
#cd /path/to/your/git/repo
git pull

# Building Docker image
echo "Building Docker image..."
docker build -t map_respublika_alert_notifier -f respublika_alert_notifier/Dockerfile .

# Stopping and removing the old container (if exists)
echo "Stopping and removing old container..."
docker stop map_respublika_alert_notifier || true
docker rm map_respublika_alert_notifier || true

# Deploying the new container
echo "Deploying new container..."
docker run --name map_respublika_alert_notifier \
    --restart unless-stopped \
    --network=jaam -d \
    --env REDIS_HOST="$REDIS_HOST" \
    --env REDIS_PASSWORD="$REDIS_PASSWORD" \
    --env REDIS_DB="$REDIS_DB" \
    --env RESPUBLIKA_ALERTS_WEBHOOK_URL="$RESPUBLIKA_ALERTS_WEBHOOK_URL" \
    --env POLL_PERIOD="$POLL_PERIOD" \
    --env TEST_MODE="$TEST_MODE" \
    --env LOGGING="$LOGGING" \
    map_respublika_alert_notifier

echo "Container deployed successfully!"
