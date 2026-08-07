#!/usr/bin/env python3
"""Remove successfully emailed incoming fax TIFFs after the retention window."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path


FAX_FILENAME = re.compile(r"fax[0-9]+\.tif")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--retention-days", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", type=int, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.retention_days < 1:
        parser.error("--retention-days must be at least 1")

    result = cleanup_received_faxes(
        retention_days=args.retention_days,
        dry_run=args.dry_run,
        now=args.now,
    )
    print(
        "fax retention complete: "
        f"checked={result['checked']} eligible={result['eligible']} "
        f"purged={result['purged']} skipped={result['skipped']}"
    )
    return 0


def cleanup_received_faxes(
    *,
    retention_days: int,
    dry_run: bool = False,
    now: int | None = None,
    state_root: Path | None = None,
    recvq_root: Path | None = None,
    backup_recvq_root: Path | None = None,
) -> dict[str, int]:
    now = int(time.time()) if now is None else int(now)
    cutoff = now - retention_days * 86400
    state_root = Path(
        state_root
        or os.environ.get(
            "FAXMAIL_STATE_DIR",
            "/var/spool/hylafax/status/kaosgdd-faxmail",
        )
    )
    recvq_root = Path(
        recvq_root
        or os.environ.get("FAXMAIL_RECVQ_DIR", "/var/spool/hylafax/recvq")
    ).resolve()
    backup_recvq_root = Path(
        backup_recvq_root
        or os.environ.get("FAXMAIL_BACKUP_RECVQ_DIR", "/srv/kaos/backups/faxmail/recvq")
    ).resolve()

    result = {"checked": 0, "eligible": 0, "purged": 0, "skipped": 0}
    sent_root = state_root / "sent"
    failed_root = state_root / "failed"
    if not sent_root.is_dir():
        return result

    for marker in sorted(sent_root.glob("*.json")):
        result["checked"] += 1
        payload = read_marker(marker)
        sent_at = integer(payload.get("sentAt"))
        if not sent_at or sent_at > cutoff or payload.get("purgedAt"):
            result["skipped"] += 1
            continue
        if (failed_root / marker.name).is_file():
            result["skipped"] += 1
            continue

        source = Path(str(payload.get("source") or ""))
        if not valid_recvq_source(source, recvq_root):
            result["skipped"] += 1
            continue

        result["eligible"] += 1
        backup = backup_recvq_root / source.name
        if dry_run:
            print(f"would purge: {source} and {backup}")
            continue

        source.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        payload.update(
            {
                "purgedAt": now,
                "retentionDays": retention_days,
                "sourcePurged": True,
                "backupPurged": True,
            }
        )
        write_marker(marker, payload)
        result["purged"] += 1

    if result["purged"]:
        write_backup_manifest(backup_recvq_root)
    return result


def integer(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def valid_recvq_source(source: Path, recvq_root: Path) -> bool:
    if not FAX_FILENAME.fullmatch(source.name):
        return False
    try:
        return source.resolve().parent == recvq_root
    except OSError:
        return False


def read_marker(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_marker(path: Path, payload: dict) -> None:
    stat = path.stat()
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o640)
    try:
        os.chown(tmp, stat.st_uid, stat.st_gid)
    except PermissionError:
        pass
    os.replace(tmp, path)


def write_backup_manifest(backup_recvq_root: Path) -> None:
    manifest = backup_recvq_root.parent / "recvq-sha256.txt"
    lines = []
    if backup_recvq_root.is_dir():
        for path in sorted(backup_recvq_root.glob("fax*.tif")):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.append(f"{digest}  {path}\n")
    tmp = manifest.with_suffix(f"{manifest.suffix}.tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, manifest)


if __name__ == "__main__":
    raise SystemExit(main())
