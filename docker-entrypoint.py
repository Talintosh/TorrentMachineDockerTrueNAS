#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
import pwd
import grp
import re
from textwrap import dedent


def log(message):
    print(f"[entrypoint] {message}", flush=True)


def run(cmd, **kwargs):
    subprocess.run(cmd, check=True, **kwargs)


def ensure_group(name, gid):
    try:
        grp.getgrnam(name)
    except KeyError:
        run(["groupadd", "-o", "-g", str(gid), name])
    else:
        run(["groupmod", "-o", "-g", str(gid), name])


def ensure_user(name, uid, group, home):
    try:
        pwd.getpwnam(name)
    except KeyError:
        run(
            [
                "useradd",
                "-o",
                "-m",
                "-d",
                home,
                "-g",
                group,
                "-u",
                str(uid),
                name,
            ]
        )
    else:
        run(["usermod", "-o", "-u", str(uid), "-g", group, name])


def ensure_dirs(paths, owner):
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
        run(["chown", "-R", owner, str(path)])


def ensure_qbittorrent_config(config_file):
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(
            dedent(
                """\
                [Application]
                FileLogger\\Enabled=false

                [LegalNotice]
                Accepted=true
                """
            )
        )
        return

    text = config_file.read_text()
    if "[LegalNotice]" not in text:
        text = text.rstrip() + "\n\n[LegalNotice]\nAccepted=true\n"
    elif re.search(r"(?m)^Accepted=.*$", text):
        text = re.sub(r"(?m)^Accepted=.*$", "Accepted=true", text, count=1)
    else:
        text = text.replace("[LegalNotice]", "[LegalNotice]\nAccepted=true", 1)
    config_file.write_text(text)


def ensure_wireguard_config(config_path):
    if not config_path:
        return None
    config_file = Path(config_path)
    if config_file.exists():
        return config_file

    private_key = os.environ.get("WIREGUARD_PRIVATE_KEY", "").strip()
    if not private_key:
        raise RuntimeError(
            f"WireGuard configuration file {config_file} not found. "
            "Create it manually (see README) or supply WIREGUARD_PRIVATE_KEY so a skeleton can be generated."
        )

    address = os.environ.get("WIREGUARD_ADDRESS", "10.0.0.2/32").strip() or "10.0.0.2/32"
    dns = os.environ.get("WIREGUARD_DNS", "100.64.0.6").strip() or "100.64.0.6"

    template = dedent(
        f"""\
        [Interface]
        Address = {address}
        PrivateKey = {private_key}
        DNS = {dns}

        # Add your [Peer] section(s) below following Mullvad's WireGuard guide.
        """
    )
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(template)
    os.chmod(config_file, 0o600)
    log(f"Wrote WireGuard skeleton config to {config_file}. Remember to append your [Peer] details.")
    return config_file


def bring_up_wireguard(config_file):
    if config_file is None:
        log("WIREGUARD_CONFIG_FILE not set; skipping wireguard bring-up.")
        return

    subprocess.run(
        ["wg-quick", "down", str(config_file)],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    log(f"Bringing up WireGuard interface using {config_file}")
    run(["wg-quick", "up", str(config_file)])


def main():
    puid = int(os.environ.get("PUID", "1000"))
    pgid = int(os.environ.get("PGID", "1000"))
    profile_dir = os.environ.get("QBT_PROFILE_DIR", "/config")
    webui_port = os.environ.get("QBT_WEBUI_PORT", "9000")
    wireguard_config = os.environ.get("WIREGUARD_CONFIG_FILE", "/etc/wireguard/wg0.conf").strip()

    qbt_user = "qbittorrent"
    qbt_group = "qbittorrent"
    profile_path = Path(profile_dir.rstrip("/"))
    config_dir = profile_path / "qBittorrent" / "config"
    config_file = config_dir / "qBittorrent.conf"
    torrent_input_dir = profile_path / "TorrentInput"
    meta_input_dir = Path("/mnt/media/MetaInput")

    ensure_group(qbt_group, pgid)
    ensure_user(qbt_user, puid, qbt_group, profile_dir)

    ensure_dirs(
        [Path(profile_dir), Path("/downloads"), config_dir, torrent_input_dir],
        f"{qbt_user}:{qbt_group}",
    )
    meta_input_dir.mkdir(parents=True, exist_ok=True)
    ensure_qbittorrent_config(config_file)

    config_file = ensure_wireguard_config(wireguard_config)
    bring_up_wireguard(config_file)

    subprocess.Popen(
        ["/usr/local/bin/log-external-ip.sh"],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )
    log(
        f"Starting watch-and-move.py from {meta_input_dir} to {torrent_input_dir}"
    )
    subprocess.Popen(
        [
            "gosu",
            f"{qbt_user}:{qbt_group}",
            "/usr/local/bin/watch-and-move.py",
            str(meta_input_dir),
            str(torrent_input_dir),
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else [
        "qbittorrent-nox",
        f"--webui-port={webui_port}",
        f"--profile={profile_dir}",
    ]

    os.execvp("gosu", ["gosu", f"{qbt_user}:{qbt_group}", *args])


if __name__ == "__main__":
    main()
