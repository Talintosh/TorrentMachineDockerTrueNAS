#!/usr/bin/env bash
set -euo pipefail

WG_IF="${WG_INTERFACE:-wg0}"
WAN_IF="${WAN_INTERFACE:-eth0}"
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
WEB_PORT="${WEB_PORT:-9000}"
RESOLV_CONF="${WG_RESOLV_CONF:-/etc/resolv.conf}"

echo "[wireguard-down] Resetting iptables OUTPUT policy"
iptables -P OUTPUT ACCEPT
echo "[wireguard-down] Flushing iptables rules"
iptables -F
echo "[wireguard-down] Removing LAN web access exception"
iptables -D INPUT -i "${WAN_IF}" -p tcp --dport "${WEB_PORT}" -s "${LAN_SUBNET}" -j ACCEPT || true

if [ -f "${RESOLV_CONF}.wg-backup" ]; then
    mv "${RESOLV_CONF}.wg-backup" "${RESOLV_CONF}"
    echo "[wireguard-down] Restored DNS configuration at ${RESOLV_CONF}"
fi
