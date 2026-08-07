#!/usr/bin/env python3
"""Send a received HylaFAX TIFF as a PDF email attachment.

This script is intended to be called from HylaFAX FaxDispatch or faxrcvd. It
does not delete the source TIFF and it does not require a local mail server.
SMTP settings are read from environment variables so credentials can live in a
root-readable env file outside the repository.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import smtplib
import ssl
import subprocess
import sys
import tempfile
import time
from email.message import EmailMessage
from pathlib import Path


class ConfigError(RuntimeError):
    pass


STATE_VERSION = 1
RETRY_DELAYS_SECONDS = (300, 900, 3600, 21600)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tiff", nargs="?")
    parser.add_argument("--remote-number", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--commid", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--mark-sent", action="store_true")
    parser.add_argument("--retry-failures", action="store_true")
    args = parser.parse_args(argv[1:])

    if args.retry_failures:
        return retry_failures()
    if not args.source_tiff:
        parser.error("source_tiff is required unless --retry-failures is used")

    source = Path(args.source_tiff)
    if not source.is_file():
        print(f"source TIFF not found: {source}", file=sys.stderr)
        return 2

    delivery_key = make_delivery_key(source, args.commid)
    if args.mark_sent:
        record_sent(
            delivery_key,
            source=source,
            remote_number=args.remote_number,
            device=args.device,
            commid=args.commid,
            note="seeded from verified historical delivery",
        )
        print(f"marked delivered: {delivery_key}")
        return 0

    if sent_marker(delivery_key).is_file() and not args.force:
        print(f"already delivered; skipping duplicate: {delivery_key}")
        return 0

    try:
        config = load_config()
    except ConfigError as exc:
        record_failure(
            delivery_key,
            source=source,
            remote_number=args.remote_number,
            device=args.device,
            commid=args.commid,
            error=exc,
        )
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="kaosgdd-faxmail-incoming-") as tmp_dir:
        pdf_path = Path(tmp_dir) / f"{source.stem}.pdf"
        try:
            convert_tiff_to_pdf(source, pdf_path)
        except RuntimeError as exc:
            record_failure(
                delivery_key,
                source=source,
                remote_number=args.remote_number,
                device=args.device,
                commid=args.commid,
                error=exc,
            )
            print(f"conversion failed: {exc}", file=sys.stderr)
            return 1

        message = build_message(
            config=config,
            pdf_path=pdf_path,
            source=source,
            remote_number=args.remote_number,
            device=args.device,
            commid=args.commid,
        )
        if args.dry_run:
            print(f"dry-run ok: would send {pdf_path.name} to {config['to_addr']}")
            return 0
        try:
            send_message(config, message)
        except (OSError, smtplib.SMTPException) as exc:
            record_failure(
                delivery_key,
                source=source,
                remote_number=args.remote_number,
                device=args.device,
                commid=args.commid,
                error=exc,
            )
            print(f"mail delivery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        record_sent(
            delivery_key,
            source=source,
            remote_number=args.remote_number,
            device=args.device,
            commid=args.commid,
        )
        print(f"sent incoming fax PDF to {config['to_addr']}: {pdf_path.name}")
        return 0


def load_config() -> dict[str, str | int | bool]:
    required = {
        "FAXMAIL_SMTP_HOST": "smtp_host",
        "FAXMAIL_FROM": "from_addr",
        "FAXMAIL_TO": "to_addr",
    }
    config: dict[str, str | int | bool] = {}
    for env_name, key in required.items():
        value = os.environ.get(env_name, "").strip()
        if not value:
            raise ConfigError(f"{env_name} is required")
        config[key] = value

    try:
        config["smtp_port"] = int(os.environ.get("FAXMAIL_SMTP_PORT", "587"))
    except ValueError as exc:
        raise ConfigError("FAXMAIL_SMTP_PORT must be an integer") from exc
    config["smtp_user"] = os.environ.get("FAXMAIL_SMTP_USER", "").strip()
    config["smtp_password"] = os.environ.get("FAXMAIL_SMTP_PASSWORD", "")
    config["smtp_starttls"] = env_bool("FAXMAIL_SMTP_STARTTLS", default=True)
    config["smtp_ssl"] = env_bool("FAXMAIL_SMTP_SSL", default=False)
    if config["smtp_ssl"] and config["smtp_starttls"]:
        raise ConfigError("FAXMAIL_SMTP_SSL and FAXMAIL_SMTP_STARTTLS cannot both be enabled")
    config["subject_prefix"] = os.environ.get("FAXMAIL_SUBJECT_PREFIX", "Incoming fax").strip()
    return config


def env_bool(name: str, *, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def convert_tiff_to_pdf(source: Path, output: Path) -> None:
    result = subprocess.run(
        ["tiff2pdf", "-o", str(output), str(source)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        reason = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(reason or "tiff2pdf failed")
    if not output.is_file() or output.stat().st_size == 0:
        raise RuntimeError("tiff2pdf did not create a PDF")


def build_message(
    *,
    config: dict[str, str | int | bool],
    pdf_path: Path,
    source: Path,
    remote_number: str,
    device: str,
    commid: str,
) -> EmailMessage:
    subject_prefix = str(config["subject_prefix"])
    remote = remote_number.strip() or "unknown"
    subject = f"{subject_prefix} from {remote}"

    message = EmailMessage()
    message["From"] = str(config["from_addr"])
    message["To"] = str(config["to_addr"])
    message["Subject"] = subject
    message.set_content(
        "\n".join(
            [
                "Incoming fax received.",
                "",
                f"Remote number: {remote}",
                f"Device: {device or 'unknown'}",
                f"Communication ID: {commid or 'unknown'}",
                f"Source TIFF: {source}",
                "",
            ]
        )
    )

    content_type, _encoding = mimetypes.guess_type(str(pdf_path))
    maintype, subtype = (content_type or "application/pdf").split("/", 1)
    message.add_attachment(
        pdf_path.read_bytes(),
        maintype=maintype,
        subtype=subtype,
        filename=pdf_path.name,
    )
    return message


def send_message(config: dict[str, str | int | bool], message: EmailMessage) -> None:
    host = str(config["smtp_host"])
    port = int(config["smtp_port"])
    user = str(config["smtp_user"])
    password = str(config["smtp_password"])

    if bool(config["smtp_ssl"]):
        smtp = smtplib.SMTP_SSL(host, port, timeout=30, context=ssl.create_default_context())
    else:
        smtp = smtplib.SMTP(host, port, timeout=30)
    with smtp:
        smtp.ehlo()
        if bool(config["smtp_starttls"]) and not bool(config["smtp_ssl"]):
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
        if user:
            smtp.login(user, password)
        smtp.send_message(message)


def state_root() -> Path:
    return Path(
        os.environ.get(
            "FAXMAIL_STATE_DIR",
            "/var/spool/hylafax/status/kaosgdd-faxmail",
        )
    )


def make_delivery_key(source: Path, commid: str) -> str:
    raw = commid.strip() or source.stem
    key = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-.")
    return key or source.stem


def sent_marker(delivery_key: str) -> Path:
    return state_root() / "sent" / f"{delivery_key}.json"


def failure_marker(delivery_key: str) -> Path:
    return state_root() / "failed" / f"{delivery_key}.json"


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.chmod(tmp, 0o640)
    os.replace(tmp, path)


def delivery_payload(
    *,
    delivery_key: str,
    source: Path,
    remote_number: str,
    device: str,
    commid: str,
) -> dict:
    return {
        "version": STATE_VERSION,
        "deliveryKey": delivery_key,
        "source": str(source.resolve()),
        "remoteNumber": remote_number.strip() or "unknown",
        "device": device.strip() or "unknown",
        "commid": commid.strip(),
    }


def record_sent(
    delivery_key: str,
    *,
    source: Path,
    remote_number: str,
    device: str,
    commid: str,
    note: str = "",
) -> None:
    payload = delivery_payload(
        delivery_key=delivery_key,
        source=source,
        remote_number=remote_number,
        device=device,
        commid=commid,
    )
    payload["sentAt"] = int(time.time())
    if note:
        payload["note"] = note
    write_json(sent_marker(delivery_key), payload)
    failure_marker(delivery_key).unlink(missing_ok=True)


def record_failure(
    delivery_key: str,
    *,
    source: Path,
    remote_number: str,
    device: str,
    commid: str,
    error: Exception,
) -> None:
    marker = failure_marker(delivery_key)
    previous = read_json(marker)
    attempts = int(previous.get("attempts", 0)) + 1
    delay = RETRY_DELAYS_SECONDS[min(attempts - 1, len(RETRY_DELAYS_SECONDS) - 1)]
    payload = delivery_payload(
        delivery_key=delivery_key,
        source=source,
        remote_number=remote_number,
        device=device,
        commid=commid,
    )
    payload.update(
        {
            "attempts": attempts,
            "lastAttemptAt": int(time.time()),
            "nextAttemptAt": int(time.time()) + delay,
            "lastErrorType": type(error).__name__,
            "lastError": str(error)[:500],
        }
    )
    write_json(marker, payload)


def retry_failures() -> int:
    failed_root = state_root() / "failed"
    if not failed_root.is_dir():
        print("no failed fax deliveries")
        return 0

    now = int(time.time())
    attempted = 0
    remaining_failures = 0
    for marker in sorted(failed_root.glob("*.json")):
        payload = read_json(marker)
        delivery_key = str(payload.get("deliveryKey") or marker.stem)
        if sent_marker(delivery_key).is_file():
            marker.unlink(missing_ok=True)
            continue
        if int(payload.get("nextAttemptAt", 0)) > now:
            continue
        source = Path(str(payload.get("source", "")))
        if not source.is_file():
            remaining_failures += 1
            print(f"retry source missing: {source}", file=sys.stderr)
            continue
        attempted += 1
        result = main(
            [
                sys.argv[0],
                str(source),
                "--remote-number",
                str(payload.get("remoteNumber", "")),
                "--device",
                str(payload.get("device", "")),
                "--commid",
                str(payload.get("commid", "")),
            ]
        )
        if result != 0:
            remaining_failures += 1

    print(f"fax delivery retry complete: attempted={attempted} failed={remaining_failures}")
    return 1 if remaining_failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
