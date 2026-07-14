#!/bin/sh
set -eu

echo "[entrypoint] waiting for PostgreSQL..."
python - <<'PY'
import os, sys, time
import socket

host = os.getenv("POSTGRES_HOST", "postgres")
port = int(os.getenv("POSTGRES_PORT", "5432"))
deadline = time.time() + 90
while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print("[entrypoint] postgres port open")
            sys.exit(0)
    except OSError:
        time.sleep(1)
print("[entrypoint] postgres not reachable", file=sys.stderr)
sys.exit(1)
PY

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

echo "[entrypoint] starting briefly runtime (bot + scheduler)"
exec python -m app.runtime
