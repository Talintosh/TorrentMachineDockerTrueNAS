#!/usr/bin/env bash
set -euo pipefail

WG_IF="${WG_INTERFACE:-wg0}"
WAN_IF="${WAN_INTERFACE:-eth0}"
WG_PORT="${WG_PORT:-51820}"
LAN_SUBNET="${LAN_SUBNET:-192.168.1.0/24}"
WEB_PORT="${WEB_PORT:-9000}"
RESOLV_CONF="${WG_RESOLV_CONF:-/etc/resolv.conf}"
DNS_SERVERS="${WIREGUARD_DNS:-100.64.0.3}"
DNS_SERVERS="${DNS_SERVERS//,/ }"

echo "[wireguard-up] Blocking all outbound traffic except ${WG_IF}"
iptables -P OUTPUT DROP

echo "[wireguard-up] Allowing loopback"
iptables -A OUTPUT -o lo -j ACCEPT

echo "[wireguard-up] Allowing established/related connections"
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

echo "[wireguard-up] Allowing WireGuard handshake packets on ${WAN_IF}:${WG_PORT}"
iptables -A OUTPUT -o "${WAN_IF}" -p udp --dport "${WG_PORT}" -j ACCEPT

echo "[wireguard-up] Allowing DNS via ${WG_IF}"
iptables -A OUTPUT -o "${WG_IF}" -p udp --dport 53 -j ACCEPT

echo "[wireguard-up] Allowing all traffic over ${WG_IF}"
iptables -A OUTPUT -o "${WG_IF}" -j ACCEPT

echo "[wireguard-up] Allowing LAN access from ${LAN_SUBNET} to web port ${WEB_PORT}"
iptables -A INPUT -i "${WAN_IF}" -p tcp --dport "${WEB_PORT}" -s "${LAN_SUBNET}" -j ACCEPT

# Ensure LAN subnet traffic is routed via the Docker/WAN interface, not the WireGuard default route
WAN_GW=""
# Try to detect the gateway for WAN_IF (e.g. 172.20.0.1 on the docker bridge)
if ip route show default 2>/dev/null | grep -q "dev ${WAN_IF}"; then
    WAN_GW="$(ip route show default 2>/dev/null | awk '/default/ && $0 ~ /dev '"${WAN_IF}"'/ {print $3; exit}')"
fi

if [ -n "${WAN_GW}" ]; then
    echo "[wireguard-up] Adding explicit LAN route ${LAN_SUBNET} via ${WAN_GW} on ${WAN_IF}"
    ip route replace "${LAN_SUBNET}" via "${WAN_GW}" dev "${WAN_IF}"
else
    echo "[wireguard-up] WARNING: Could not determine gateway for ${WAN_IF}; LAN route ${LAN_SUBNET} not added"
fi

# Allow HTTPS (external IP checks) through WireGuard
iptables -A OUTPUT -o "${WG_IF}" -p tcp --dport 443 -j ACCEPT

if [ -f "${RESOLV_CONF}" ] && [ ! -f "${RESOLV_CONF}.wg-backup" ]; then
    cp "${RESOLV_CONF}" "${RESOLV_CONF}.wg-backup"
fi

{
    for dns in ${DNS_SERVERS}; do
        [ -n "${dns}" ] && printf 'nameserver %s\n' "${dns}"
    done
} > "${RESOLV_CONF}"
echo "[wireguard-up] Updated ${RESOLV_CONF} to use WireGuard DNS: ${DNS_SERVERS}"
