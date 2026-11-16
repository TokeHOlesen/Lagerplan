#!/bin/sh
# Daily SQLite backup, keeping the last 30 days.
# Run from cron as the lagerplan user, e.g. in `sudo crontab -u lagerplan -e`:
#   15 2 * * * /srv/lagerplan/Lagerplan/deploy/backup.sh
set -eu
APP_DIR=/srv/lagerplan/Lagerplan
BACKUP_DIR="$APP_DIR/backups"
mkdir -p "$BACKUP_DIR"
# .backup makes a consistent copy even while the app is running.
sqlite3 "$APP_DIR/db.sqlite3" ".backup '$BACKUP_DIR/db-$(date +%F).sqlite3'"
find "$BACKUP_DIR" -name 'db-*.sqlite3' -mtime +30 -delete
