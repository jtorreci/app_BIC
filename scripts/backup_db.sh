#!/bin/sh
# Daily PostgreSQL dump for DIGIBIC with 30-day retention.
# Cron example (root): 30 3 * * * /opt/digibic/scripts/backup_db.sh
set -eu

APP_DIR="${APP_DIR:-/opt/digibic}"
BACKUP_DIR="${BACKUP_DIR:-/srv/backups/digibic}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
cd "$APP_DIR"

STAMP=$(date +%Y%m%d_%H%M%S)
TARGET="$BACKUP_DIR/digibic_$STAMP.sql.gz"

docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists' \
    | gzip > "$TARGET.tmp"
mv "$TARGET.tmp" "$TARGET"

find "$BACKUP_DIR" -name 'digibic_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
echo "Backup written to $TARGET"
