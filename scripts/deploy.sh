#!/usr/bin/env bash
# Manual deploy on the VPS as user deploy (same path as GitHub Actions).
# Usage: cd /opt/briefly && ./scripts/deploy.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "$(pwd)" != "/opt/briefly" ]]; then
  echo "WARN: expected /opt/briefly (pwd=$(pwd)). Continue only if intentional." >&2
fi

if [[ ! -f .env.production ]]; then
  echo "ERROR: .env.production missing." >&2
  exit 1
fi

if [[ -d .git ]]; then
  echo "[deploy] git fetch + pull main (does not modify .env.production)"
  ENV_BEFORE="$(sha256sum .env.production | awk '{print $1}')"
  git fetch origin
  git checkout main
  git pull --ff-only origin main
  ENV_AFTER="$(sha256sum .env.production | awk '{print $1}')"
  if [[ "$ENV_BEFORE" != "$ENV_AFTER" ]]; then
    echo "ERROR: .env.production changed during pull" >&2
    exit 1
  fi
fi

chmod +x scripts/ci_deploy.sh
exec ./scripts/ci_deploy.sh
