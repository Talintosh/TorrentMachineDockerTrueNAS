#!/usr/bin/env python3
"""
watch_and_move.py
------------------

Purpose:
    This script solves a common issue when using qBittorrent’s "monitored folder"
    feature on network storage (NAS: SMB, NFS, Synology, TrueNAS, etc.).

    When a file is copied onto a NAS, it often appears in the directory *before*
    it is fully written. qBittorrent sees the incomplete file, fails to read it,
    and renames it to `.qbt_rejected`.

    This script prevents that.

What it does:
    - Watches a directory (e.g., a NAS "staging" folder)
    - Detects when newly created files have finished transferring by checking:
        * file size stability
        * modification time stability
        * no changes for N seconds
    - Once stable, it *moves* the file into the destination directory
      (e.g., qBittorrent's watch folder) using an atomic rename,
      ensuring qBittorrent only ever sees fully-written files.

Why it’s required:
    SMB/NFS and cloud-synced NAS folders frequently produce partially-written
    files that cause qBittorrent to reject torrents. Moving fully written files
    into the watch folder avoids `.qbt_rejected` errors entirely.

Usage example:
    ./watch_and_move.py /nas/staging /nas/qbt_watch --extensions .torrent

Author:
    ChatGPT (generated)
"""

import argparse
import errno
import os
import shutil
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Watch a directory and move files once they are fully transferred."
    )
    parser.add_argument(
        "source",
        help="Source directory to watch (where files are being written).",
    )
    parser.add_argument(
        "destination",
        help="Destination directory (where complete files will be moved).",
    )
    parser.add_argument(
        "--stable-seconds",
        type=int,
        default=15,
        help="How many seconds a file must remain unchanged before moving (default: 15).",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Polling interval in seconds (default: 2.0).",
    )
    parser.add_argument(
        "--extensions",
        default="",
        help=(
            "Optional comma-separated list of extensions to include "
            "(e.g. '.torrent,.nzb'). If empty, all files are watched."
        ),
    )
    return parser.parse_args()


def safe_move(src: Path, dst_dir: Path):
    """
    Move src into dst_dir.
    If a file with the same name exists, append a numeric suffix.
    Always deletes the source file after a successful move/copy.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    base_target = dst_dir / src.name

    def next_target(counter: int = 0) -> Path:
        if counter == 0:
            return base_target
        stem, suffix = base_target.stem, base_target.suffix
        return base_target.with_name(f"{stem} ({counter}){suffix}")

    counter = 0
    while True:
        target = next_target(counter)
        if target.exists():
            counter += 1
            continue

        try:
            src.rename(target)
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                counter += 1
                continue
            if exc.errno != errno.EXDEV:
                raise
            # Cross-device rename; fall back to copy + delete.
            shutil.copy2(src, target)
            src.unlink()
        print(f"[MOVE] {src} -> {target}")
        return


def main():
    args = parse_args()

    source_dir = Path(args.source).resolve()
    dest_dir = Path(args.destination).resolve()

    if not source_dir.is_dir():
        raise SystemExit(f"Source directory does not exist or is not a directory: {source_dir}")

    print(f"[INFO] Watching: {source_dir}")
    print(f"[INFO] Destination: {dest_dir}")
    print(f"[INFO] Stable time: {args.stable_seconds}s, interval: {args.interval}s")

    # Normalise extensions filter
    exts = set()
    if args.extensions.strip():
        for ext in args.extensions.split(","):
            ext = ext.strip()
            if ext and not ext.startswith("."):
                ext = "." + ext
            if ext:
                exts.add(ext.lower())

        print(f"[INFO] Filtering by extensions: {sorted(exts)}")
    else:
        print("[INFO] No extension filter: all files will be watched.")

    # Tracking: path -> {size, mtime, first_seen, last_changed}
    tracked = {}

    while True:
        try:
            # List current files
            current_files = {}
            for entry in source_dir.iterdir():
                if not entry.is_file():
                    continue

                if exts:
                    if entry.suffix.lower() not in exts:
                        continue

                try:
                    stat = entry.stat()
                except FileNotFoundError:
                    # File vanished between listdir and stat; ignore this round
                    continue

                current_files[entry] = (stat.st_size, stat.st_mtime)

            now = time.time()

            # Update tracked info
            # 1) For each current file, update or create tracking entry
            for path, (size, mtime) in current_files.items():
                info = tracked.get(path)

                if info is None:
                    # New file
                    tracked[path] = {
                        "size": size,
                        "mtime": mtime,
                        "first_seen": now,
                        "last_changed": now,
                    }
                    print(f"[TRACK] New file: {path} (size={size})")
                else:
                    # Existing tracked file
                    if size != info["size"] or mtime != info["mtime"]:
                        # File changed
                        info["size"] = size
                        info["mtime"] = mtime
                        info["last_changed"] = now
                        # (Optional) log if you want noise:
                        # print(f"[UPDATE] {path} changed (size={size})")

            # 2) Move files that have been stable long enough
            to_remove = []
            for path, info in tracked.items():
                if path not in current_files:
                    # File disappeared from directory (maybe moved manually)
                    to_remove.append(path)
                    continue

                stable_for = now - info["last_changed"]
                if stable_for >= args.stable_seconds:
                    try:
                        safe_move(path, dest_dir)
                    except Exception as e:
                        print(f"[ERROR] Failed to move {path}: {e}")
                    to_remove.append(path)

            # Clean up moved/missing entries
            for path in to_remove:
                tracked.pop(path, None)

            time.sleep(args.interval)

        except KeyboardInterrupt:
            print("\n[INFO] Stopping watcher.")
            break


if __name__ == "__main__":
    main()
