# TorrentMachineDockerTrueNAS

Docker project that builds an Ubuntu 24.04 based container with `qbittorrent-nox` pre-installed and configured to auto-start whenever the container boots.

## Overview

This container bundles qBittorrent with a Mullvad WireGuard client and a hard kill-switch. Traffic only leaves over the `wg0` interface, DNS is pinned to Mullvad (100.64.0.6 by default), and a helper script logs the current public IP so you can confirm the tunnel stays active. Bind-mounted volumes keep qBittorrent state on the host so the stack survives upgrades or rebuilds.

## Requirements

- Docker and Docker Compose V2 (`docker compose ...`)
- A Mullvad account + generated WireGuard configuration (or another WireGuard provider with compatible configs)

## Deployment (start to finish)

1. **Clone & prepare directories**
   ```bash
   git clone <repo-url> TorrentMachineDockerTrueNAS
   cd TorrentMachineDockerTrueNAS
   mkdir -p config downloads wireguard
   ```
2. **Generate/import your WireGuard settings**
   - Use Mullvad’s WireGuard generator and download the `.conf`.
   - Copy the `[Interface]` block into `wireguard/wg0.conf` (or another filename if you override `WIREGUARD_CONFIG_FILE`). Only keep `Address` + `PrivateKey`; leave `DNS` commented because the container rewrites `/etc/resolv.conf` itself. Paste the `[Peer]` section verbatim so the relay hostname/public key stay intact.
   - Template for reference:
     ```ini
     [Interface]
     Address = 10.0.0.2/32
     PrivateKey = <replace-with-your-private-key>
     # DNS is managed automatically; keep this commented unless you handle resolv.conf yourself.
     #DNS = 100.64.0.6

     [Peer]
     PublicKey = <mullvad-server-public-key>
     AllowedIPs = 0.0.0.0/0
     Endpoint = <wireguard-server-hostname>:51820
     ```
   - Prefer `*.mullvad.net` hostnames ending in `-wg-` (WireGuard relays). The repository ships an example file; overwrite it with your own values.
3. **(Optional) Configure environment overrides**
   - Create a `.env` file (or export variables) to override user IDs, ports, or WireGuard parameters (listed under *Configuration reference* below). At minimum you can set:
     ```bash
     export PUID=$(id -u)
     export PGID=$(id -g)
     ```
4. **Build & run**
   ```bash
   docker compose build
   docker compose up -d
   ```
   The first start may take a minute: the container brings up `wg0`, applies iptables rules, rewrites `/etc/resolv.conf`, launches qBittorrent, and starts the external-IP logger.
5. **Verify the VPN & DNS**
   ```bash
   docker compose exec qbittorrent curl https://am.i.mullvad.net/connected
   docker compose exec qbittorrent wg show
   docker compose logs qbittorrent | grep external-ip
   ```
   You should see Mullvad reporting “You are connected” and the wireguard interface showing recent handshakes. The log stream prints `[external-ip] …` lines every minute.
6. **Access the UI** at `http://<host-ip>:9000` (default credentials `admin` / `adminadmin`; change them immediately under Preferences → Web UI).
7. **(Optional) Debug shell** – `./run-debug.py` or `docker compose exec qbittorrent bash` drops you inside the container as `appuser`.

### Shell access

- Attach to the running container:
  ```bash
  docker compose exec qbittorrent bash
  ```
- Start a one-off shell without the daemon (stops when you exit):
  ```bash
  docker compose run --rm qbittorrent bash
  ```

## Configuration reference

- `./config` is mounted at `/config` inside the container and stores qBittorrent state.
- `./downloads` is mounted at `/downloads` for completed downloads.
- `./wireguard` is mounted at `/etc/wireguard` and stores the Mullvad-generated WireGuard `.conf` files plus optional secrets like the `account` file. Leave the `DNS=` line commented inside those configs; `/usr/local/bin/wg-up.sh` already rewrites `resolv.conf` to use Mullvad DNS and `wg-quick` will fail if it tries to manage DNS itself in this minimal container.
- Customize the container user/group IDs or the exposed Web UI port via environment variables in `docker-compose.yml` (`PUID`, `PGID`, `QBT_WEBUI_PORT`, `QBT_PROFILE_DIR`). WireGuard behaviour is controlled with:
  - `WIREGUARD_CONFIG_FILE` – path to the config inside the container (default `/etc/wireguard/wg0.conf`).
  - `WIREGUARD_PRIVATE_KEY` – optional helper to auto-populate the `[Interface]` block if the config file doesn’t exist yet.
  - `WIREGUARD_ADDRESS` / `WIREGUARD_DNS` – defaults `10.0.0.2/32` and `100.64.0.6` when generating the `[Interface]` block from env vars.
  - `WG_INTERFACE`, `WAN_INTERFACE`, `WG_PORT`, `WG_RESOLV_CONF` – passed into `/usr/local/bin/wg-up.sh`/`wg-down.sh` to control which interfaces/ports the kill-switch script uses and which `resolv.conf` file gets rewritten (defaults: `wg0`, `eth0`, `51820`, `/etc/resolv.conf`).
- External IP logging (every minute) can be tuned with:
  - `IP_CHECK_INTERVAL` – seconds between checks (default `60`).
  - `IP_CHECK_URL` – endpoint that returns your public IP (default `https://am.i.mullvad.net/ip`).

## Mullvad WireGuard workflow & leak protection

The container still follows Mullvad’s [WireGuard on Linux terminal (advanced)](https://mullvad.net/en/help/wireguard-and-mullvad-vpn) flow, but it now expects you to manage the `.conf` file yourself:

1. You generate/export your own WireGuard keys and Mullvad server settings, then write them into `wireguard/wg0.conf` (see the template above). The entrypoint can optionally scaffold the `[Interface]` block via `WIREGUARD_PRIVATE_KEY`, `WIREGUARD_ADDRESS` (default `10.0.0.2/32`), and `WIREGUARD_DNS` (default `100.64.0.6`). It never touches your `[Peer]` definition, so append those lines manually.
2. On startup the entrypoint ensures the config file exists and then runs `wg-quick up /etc/wireguard/wg0.conf` (or whichever path you set in `WIREGUARD_CONFIG_FILE`). Compose already grants `NET_ADMIN`, `/dev/net/tun`, and `net.ipv4.conf.all.src_valid_mark=1`.
3. As part of the `PostUp`/`PreDown` hooks the container executes `/usr/local/bin/wg-up.sh` and `/usr/local/bin/wg-down.sh`. These scripts enforce the kill-switch policy (only `wg0` traffic is allowed, LAN web access is explicitly whitelisted) and rewrite `/etc/resolv.conf` to point at Mullvad (`100.64.0.6` by default) so every lookup travels through the tunnel. When the tunnel shuts down, the original DNS configuration is restored. The scripts also log every change so you can audit iptables/DNS behaviour in `docker compose logs`.

Verify the VPN from inside the container:

```bash
docker compose exec qbittorrent curl https://am.i.mullvad.net/connected
docker compose exec qbittorrent wg show
```

To customize the kill switch (e.g., different LAN CIDR or additional allowed ports), edit `wireguard/up.sh` / `down.sh`. Because all WireGuard files live in `./wireguard`, changes persist across rebuilds and are easy to version-control.
