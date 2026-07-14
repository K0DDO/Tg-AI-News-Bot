#!/usr/bin/env bash
# Pre-install VPS checks for Briefly. Does NOT change VPN / iptables / ports.
set -euo pipefail

echo "======== Briefly VPS check ========"
echo "Host: $(hostname)"
echo "Date: $(date -Is)"
echo

echo "--- Linux ---"
if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  echo "OS: ${PRETTY_NAME:-unknown}"
else
  uname -a
fi
echo "Kernel: $(uname -r)"

echo
echo "--- Memory ---"
if command -v free >/dev/null; then
  free -h
  AVAIL_MB="$(free -m | awk '/Mem:/ {print $7}')"
  if [[ "${AVAIL_MB:-0}" -lt 400 ]]; then
    echo "WARN: available RAM < 400MB — start may OOM. Free memory or reduce other services."
  fi
else
  echo "free: not found"
fi

echo
echo "--- Disk ---"
df -h / /opt 2>/dev/null || df -h /

echo
echo "--- Docker ---"
if command -v docker >/dev/null; then
  docker --version
  docker compose version 2>/dev/null || docker-compose --version 2>/dev/null || echo "WARN: compose plugin missing"
else
  echo "ERROR: Docker is not installed"
fi

echo
echo "--- Amnezia / VPN (informational; do not change) ---"
if command -v docker >/dev/null; then
  docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null | grep -iE 'amnezia|awg|wireguard|xray|openvpn' || echo "No obvious Amnezia containers in docker ps"
fi
ss -lntu 2>/dev/null | head -n 40 || netstat -lntu 2>/dev/null | head -n 40 || true
echo
echo "NOTE: Briefly compose publishes NO host ports for Postgres/Redis/App."
echo "NOTE: Do not edit iptables / Amnezia rules for this deploy."

echo
echo "--- Recommendations ---"
echo "1. Install Docker Engine + Compose plugin if missing."
echo "2. Place project at /opt/briefly with .env (secrets)."
echo "3. Keep EMBEDDING_BACKEND=hashing on 2GB VPS."
echo "4. Leave ~512MB+ free for Amnezia + OS."
echo "5. If a port conflict appears, do NOT auto-fix — resolve manually."
echo "======== check complete ========"
