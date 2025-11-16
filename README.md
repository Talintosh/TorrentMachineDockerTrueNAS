# TorrentMachineDockerTrueNAS

Docker project that builds an Ubuntu 24.04 based container with `qbittorrent-nox` pre-installed and configured to auto-start whenever the container boots.

## Requirements

- Docker and Docker Compose V2 (`docker compose ...`)

## Initialization

1. Clone/download this repo on the host that will run Docker.
2. (Optional, but tidy) Create bind-mount directories ahead of time:
   ```bash
   mkdir -p config downloads wireguard
   ```
3. Build the image (this happens automatically on first `up`, but you can do it manually):
   ```bash
   docker compose build
   ```

## Usage

1. Create the WireGuard configuration in `wireguard/wg0.conf` (or another filename if you override `WIREGUARD_CONFIG_FILE`). Start with the interface section below—fill in your private key and append your `[Peer]` section(s) from the Mullvad guide:
   ```ini
   [Interface]
   Address = 10.0.0.2/32
   PrivateKey = <replace-with-your-private-key>
   # DNS is managed automatically; keep this commented unless you handle resolv.conf yourself.
   #DNS = 100.64.0.6

   # Add your [Peer] section here, for example:
   # [Peer]
   # PublicKey = <mullvad-server-public-key>
   # AllowedIPs = 0.0.0.0/0, ::/0
   # Endpoint = <server-hostname>:51820
   ```
   > Tip: if you prefer setting secrets via environment variables, export `WIREGUARD_PRIVATE_KEY` (plus optional `WIREGUARD_ADDRESS` / `WIREGUARD_DNS`) before `docker compose up` and the entrypoint will generate the `[Interface]` block automatically when the config file is missing.
2. Build and start the container:
   ```bash
   docker compose up -d
   ```
3. Open the qBittorrent Web UI at `http://<host-ip>:8080`. The default credentials are the upstream defaults (`admin` / `adminadmin`) until you change them in the UI.
4. (Optional) Run `./run-debug.py` to automate the setup/build/up steps and drop into an interactive shell inside the running container as the non-root `appuser`.

### Shell access

- Attach to the running container:
  ```bash
  docker compose exec qbittorrent bash
  ```
- Start a one-off shell without the daemon (stops when you exit):
  ```bash
  docker compose run --rm qbittorrent bash
  ```

### Configuration

- `./config` is mounted at `/config` inside the container and stores qBittorrent state.
- `./downloads` is mounted at `/downloads` for completed downloads.
- `./wireguard` is mounted at `/etc/wireguard` and stores the Mullvad-generated WireGuard `.conf` files plus optional secrets like the `account` file. Leave the `DNS=` line commented inside those configs; `/etc/wireguard/up.sh` already rewrites `resolv.conf` to use Mullvad DNS and `wg-quick` will fail if it tries to manage DNS itself in this minimal container.
- Customize the container user/group IDs or the exposed Web UI port via environment variables in `docker-compose.yml` (`PUID`, `PGID`, `QBT_WEBUI_PORT`, `QBT_PROFILE_DIR`). WireGuard behaviour is controlled with:
  - `WIREGUARD_CONFIG_FILE` – path to the config inside the container (default `/etc/wireguard/wg0.conf`).
  - `WIREGUARD_PRIVATE_KEY` – optional helper to auto-populate the `[Interface]` block if the config file doesn’t exist yet.
  - `WIREGUARD_ADDRESS` / `WIREGUARD_DNS` – defaults `10.0.0.2/32` and `100.64.0.6` when generating the `[Interface]` block from env vars.
  - `WG_INTERFACE`, `WAN_INTERFACE`, `WG_PORT`, `WG_RESOLV_CONF` – passed into `/etc/wireguard/up.sh`/`down.sh` to control which interfaces/ports the kill-switch script uses and which `resolv.conf` file gets rewritten (defaults: `wg0`, `eth0`, `51820`, `/etc/resolv.conf`).
- External IP logging (every minute) can be tuned with:
  - `IP_CHECK_INTERVAL` – seconds between checks (default `60`).
  - `IP_CHECK_URL` – endpoint that returns your public IP (default `https://am.i.mullvad.net/ip`).

### Mullvad WireGuard workflow

The container still follows Mullvad’s [WireGuard on Linux terminal (advanced)](https://mullvad.net/en/help/wireguard-and-mullvad-vpn) flow, but it now expects you to manage the `.conf` file yourself:

1. You generate/export your own WireGuard keys and Mullvad server settings, then write them into `wireguard/wg0.conf` (see the template above). The entrypoint can optionally scaffold the `[Interface]` block via `WIREGUARD_PRIVATE_KEY`, `WIREGUARD_ADDRESS` (default `10.0.0.2/32`), and `WIREGUARD_DNS` (default `1.1.1.1`). It never touches your `[Peer]` definition, so append those lines manually.
2. On startup the entrypoint ensures the config file exists and then runs `wg-quick up /etc/wireguard/wg0.conf` (or whichever path you set in `WIREGUARD_CONFIG_FILE`). Compose already grants `NET_ADMIN`, `/dev/net/tun`, and `net.ipv4.conf.all.src_valid_mark=1`.
3. As part of the `PostUp`/`PreDown` hooks the container executes `/etc/wireguard/up.sh` and `/etc/wireguard/down.sh`. These scripts enforce the kill-switch policy (only `wg0` traffic is allowed, LAN web access is explicitly whitelisted) and rewrite `/etc/resolv.conf` to point at Mullvad (`100.64.0.6` by default) so every lookup travels through the tunnel. When the tunnel shuts down, the original DNS configuration is restored. After the tunnel, firewall, and DNS settings are in place, the entrypoint remaps the qBittorrent user/group IDs, ensures the legal notice is accepted, and launches `qbittorrent-nox`.

Verify the VPN from inside the container:

```bash
docker compose exec qbittorrent curl https://am.i.mullvad.net/connected
docker compose exec qbittorrent wg show
```

To add kill switches or LAN exceptions, edit `wireguard/wg0.conf` according to Mullvad’s guide (e.g. append `PostUp`/`PreDown` iptables rules). Because the directory is bind-mounted, your edits persist across rebuilds.
