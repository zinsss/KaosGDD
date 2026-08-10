#!/usr/bin/env python3
"""Remove incoming fax TIFFs after confirmed Telegram archival and retention."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path


FAX_FILENAME = re.compile(r"fax([0-9]+)\.tif", re.IGNORECASE)


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
    telegram_state_path: Path | None = None,
    recvq_root: Path | None = None,
    backup_recvq_root: Path | None = None,
) -> dict[str, int]:
    now = int(time.time()) if now is None else int(now)
    cutoff = now - retention_days * 86400
    telegram_state_path = Path(
        telegram_state_path
        or os.environ.get(
            "FAX_TELEGRAM_ARCHIVE_STATE_PATH",
            "/srv/kaos/data/kaosgdd/brain/faxmail/telegram-archive.json",
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
    archive_state = read_json(telegram_state_path)
    archived = archive_state.get("archived")
    if not isinstance(archived, dict) or not recvq_root.is_dir():
        return result

    for source in sorted(recvq_root.glob("fax*.tif")):
        match = FAX_FILENAME.fullmatch(source.name)
        if not match:
            continue
        result["checked"] += 1
        archive = received_archive_record(archived, source, match.group(1))
        archived_at = timestamp(archive.get("at")) if archive else 0
        if not archive or archive.get("status") != "uploaded" or not archived_at:
            result["skipped"] += 1
            continue
        if archived_at > cutoff:
            result["skipped"] += 1
            continue
        if source.resolve().parent != recvq_root:
            result["skipped"] += 1
            continue

        result["eligible"] += 1
        backup = backup_recvq_root / source.name
        if dry_run:
            print(f"would purge: {source} and {backup}")
            continue

        source.unlink(missing_ok=True)
        backup.unlink(missing_ok=True)
        result["purged"] += 1

    if result["purged"]:
        write_backup_manifest(backup_recvq_root)
    return result


def received_archive_record(archived: dict, source: Path, sequence: str) -> dict:
    for key in (f"received:{sequence}", f"received:{source.stem}"):
        value = archived.get(key)
        if isinstance(value, dict):
            return value
    return {}


def timestamp(value) -> int:
    raw = str(value or "").strip()
    if not raw:
        return 0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


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
