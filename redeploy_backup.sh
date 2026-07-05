#!/bin/bash

# Контейнер бекапу PostgreSQL → Cloudflare R2

DB_PASSWORD=""
R2_ACCOUNT_ID=""
R2_ACCESS_KEY_ID=""
R2_SECRET_ACCESS_KEY=""
R2_BUCKET="jaam-backups"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -p|--db-password)     DB_PASSWORD="$2";         shift 2;;
        -id|--account-id)     R2_ACCOUNT_ID="$2";       shift 2;;
        -ak|--access-key)     R2_ACCESS_KEY_ID="$2";    shift 2;;
        -sk|--secret-key)     R2_SECRET_ACCESS_KEY="$2"; shift 2;;
        -b|--bucket)          R2_BUCKET="$2";            shift 2;;
        *) echo "Unknown argument: $1"; exit 1;;
    esac
done

if [[ -z "$DB_PASSWORD" || -z "$R2_ACCOUNT_ID" || -z "$R2_ACCESS_KEY_ID" || -z "$R2_SECRET_ACCESS_KEY" ]]; then
    echo "Error: -p, -id, -ak, -sk are required"
    exit 1
fi

echo "BACKUP"
echo "R2_BUCKET:     $R2_BUCKET"
echo "R2_ACCOUNT_ID: $R2_ACCOUNT_ID"
echo "DB_PASSWORD:   ******"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker stop jaam-backup 2>/dev/null || true
docker rm   jaam-backup 2>/dev/null || true

echo "Building backup image..."
docker build -t jaam-backup "$SCRIPT_DIR/admin_panel/backup/"

echo "Starting backup container..."
docker run -d \
    --name jaam-backup \
    --network jaam \
    --restart unless-stopped \
    --env DB_PASSWORD="$DB_PASSWORD" \
    --env R2_ACCOUNT_ID="$R2_ACCOUNT_ID" \
    --env R2_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
    --env R2_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
    --env R2_BUCKET="$R2_BUCKET" \
    jaam-backup

echo "Container deployed successfully!"
echo "Run 'docker exec jaam-backup /backup.sh' to trigger a manual backup."
