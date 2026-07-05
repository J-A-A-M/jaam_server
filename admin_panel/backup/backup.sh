#!/usr/bin/env bash
set -euo pipefail

FILENAME="jaam_admin_$(date -u +%Y-%m-%d_%H-%M).sql.gz"
TMPFILE="/tmp/${FILENAME}"

echo "$(date -u) Starting backup: $FILENAME"

PGPASSWORD="$DB_PASSWORD" pg_dump -h postgres -U jaam jaam_admin | gzip > "$TMPFILE"

rclone copy "$TMPFILE" "r2:${R2_BUCKET}/backups/"
rm -f "$TMPFILE"

# Видаляємо файли старіші 30 днів (720 годин)
rclone delete --min-age 720h "r2:${R2_BUCKET}/backups/"

echo "$(date -u) Backup OK: $FILENAME"
