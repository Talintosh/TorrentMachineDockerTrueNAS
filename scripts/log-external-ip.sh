#!/usr/bin/env bash
set -euo pipefail

URL="${IP_CHECK_URL:-https://am.i.mullvad.net/ip}"
SLEEP="${IP_CHECK_INTERVAL:-60}"

log() {
    printf '[external-ip] %s\n' "$*"
}

while true; do
    ts="$(date --iso-8601=seconds || date)"
    ip="$(curl -fsS "${URL}" || echo "unavailable")"
    log "${ts} -> ${ip}"
    sleep "${SLEEP}"
done
