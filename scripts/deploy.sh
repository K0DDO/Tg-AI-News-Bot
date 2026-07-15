#!/usr/bin/env bash
# Simple deploy on VPS: pull → build → migrate (entrypoint) → up → health check.
# Usage (on server):  /opt/briefly/scripts/deploy.sh
# Or via SSH from CI: ssh user@host 'cd /opt/briefly && ./scripts/deploy.sh'
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[deploy] root=$ROOT"
if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production missing. Copy .env.production.example and fill secrets." >&2
  exit 1
fi

echo "[deploy] git pull (if repo)"
if [[ -d .git ]]; then
  git fetch --all --prune
  git pull --ff-only
fi

echo "[deploy] build + up"
export COMPOSE_ENV_FILE=".env.production"
docker compose --env-file .env.production build briefly-app
docker compose --env-file .env.production up -d postgres redis
docker compose --env-file .env.production up -d --force-recreate briefly-app

echo "[deploy] waiting for containers..."
sleep 5
docker compose --env-file .env.production ps

echo "[deploy] recent app logs"
docker compose --env-file .env.production logs --tail=80 briefly-app || true

# Optional nightly cron for backups (idempotent hint)
CRON_LINE="15 3 * * * cd $ROOT && ./scripts/backup_postgres.sh >> $ROOT/logs/backup.log 2>&1"
if command -v crontab >/dev/null; then
  if ! crontab -l 2>/dev/null | grep -F "backup_postgres.sh" >/dev/null; then
    echo "[deploy] TIP: add cron:"
    echo "  $CRON_LINE"
  fi
fi

echo "[deploy] done"
