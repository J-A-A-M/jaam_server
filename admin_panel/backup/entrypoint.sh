#!/usr/bin/env bash
set -euo pipefail

: "${R2_ACCOUNT_ID:?R2_ACCOUNT_ID is required}"
: "${R2_ACCESS_KEY_ID:?R2_ACCESS_KEY_ID is required}"
: "${R2_SECRET_ACCESS_KEY:?R2_SECRET_ACCESS_KEY is required}"
: "${R2_BUCKET:?R2_BUCKET is required}"
: "${DB_PASSWORD:?DB_PASSWORD is required}"

mkdir -p /root/.config/rclone
cat > /root/.config/rclone/rclone.conf <<EOF
[r2]
type = s3
provider = Cloudflare
access_key_id = ${R2_ACCESS_KEY_ID}
secret_access_key = ${R2_SECRET_ACCESS_KEY}
endpoint = https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com
no_check_bucket = true
EOF

# Setup busybox crond (built into Alpine, no extra packages needed)
mkdir -p /var/spool/cron/crontabs
printf '0 6,18 * * *\t/backup.sh\n' > /var/spool/cron/crontabs/root
chmod 0600 /var/spool/cron/crontabs/root

echo "$(date -u) Backup container started. Schedule: 06:00 and 18:00 UTC."

# -f: foreground, -l 8: log level (8=debug, shows job execution)
exec busybox crond -f -l 8
