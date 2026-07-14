#!/usr/bin/env bash
# Simple deploy on VPS: pull → build → migrate (entrypoint) → up → health check.
# Usage (on server):  /opt/briefly/scripts/deploy.sh
# Or via SSH from CI: ssh user@host 'cd /opt/briefly && ./scripts/deploy.sh'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[deploy] root=$ROOT"
if [[ ! -f .env ]]; then
  echo "ERROR: .env missing. Copy .env.example and fill secrets." >&2
  exit 1
fi

echo "[deploy] git pull (if repo)"
if [[ -d .git ]]; then
  git fetch --all --prune
  git pull --ff-only
fi

echo "[deploy] build + up"
docker compose build briefly-app
docker compose up -d postgres redis
docker compose up -d --force-recreate briefly-app

echo "[deploy] waiting for containers..."
sleep 5
docker compose ps

echo "[deploy] recent app logs"
docker compose logs --tail=80 briefly-app || true

# Optional nightly cron for backups (idempotent hint)
CRON_LINE="15 3 * * * cd $ROOT && ./scripts/backup_postgres.sh >> $ROOT/logs/backup.log 2>&1"
if command -v crontab >/dev/null; then
  if ! crontab -l 2>/dev/null | grep -F "backup_postgres.sh" >/dev/null; then
    echo "[deploy] TIP: add cron:"
    echo "  $CRON_LINE"
  fi
fi

echo "[deploy] done"
