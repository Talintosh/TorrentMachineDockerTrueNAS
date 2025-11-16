#!/usr/bin/env python3
import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICE_NAME = os.environ.get("SERVICE_NAME", "qbittorrent")
CONTAINER_NAME = os.environ.get("CONTAINER_NAME", SERVICE_NAME)
PUID = os.environ.get("PUID", "1000")
PGID = os.environ.get("PGID", "1000")
WAIT_TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "60"))
APP_USER = os.environ.get("EXEC_USER", "appuser")


def run(cmd, **kwargs):
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True, **kwargs)


def ensure_dirs():
    for rel in ("config", "downloads"):
        path = ROOT / rel
        path.mkdir(parents=True, exist_ok=True)
        run(["chown", "-R", f"{PUID}:{PGID}", str(path)])
    wireguard = ROOT / "wireguard"
    wireguard.mkdir(parents=True, exist_ok=True)


def wait_for_container():
    deadline = time.time() + WAIT_TIMEOUT
    while True:
        try:
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Status}}", CONTAINER_NAME],
                check=False,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:  # docker missing
            raise RuntimeError("docker executable not found") from exc

        status = result.stdout.strip()
        if result.returncode == 0 and status == "running":
            return

        if time.time() >= deadline:
            raise TimeoutError(
                f"Container '{CONTAINER_NAME}' did not reach running state within {WAIT_TIMEOUT}s "
                f"(last status: {status or 'unknown'})"
            )
        time.sleep(1)


def main():
    ensure_dirs()
    run(["docker", "compose", "build", SERVICE_NAME])
    run(["docker", "compose", "up", "-d", SERVICE_NAME])
    print(f"Waiting for container '{CONTAINER_NAME}' to be running...")
    wait_for_container()
    print("Container is running; opening shell...")
    run(["docker", "compose", "exec", "--user", APP_USER, SERVICE_NAME, "bash"])


if __name__ == "__main__":
    main()
