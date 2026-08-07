#!/usr/bin/env python3
"""Send a received HylaFAX TIFF as a PDF email attachment.

This script is intended to be called from HylaFAX FaxDispatch or faxrcvd. It
does not delete the source TIFF and it does not require a local mail server.
SMTP settings are read from environment variables so credentials can live in a
root-readable env file outside the repository.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import smtplib
import ssl
import subprocess
import sys
import tempfile
from email.message import EmailMessage
from pathlib import Path


class ConfigError(RuntimeError):
    pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tiff")
    parser.add_argument("--remote-number", default="")
    parser.add_argument("--device", default="")
    parser.add_argument("--commid", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv[1:])

    source = Path(args.source_tiff)
    if not source.is_file():
        print(f"source TIFF not found: {source}", file=sys.stderr)
        return 2

    try:
        config = load_config()
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    with tempfile.TemporaryDirectory(prefix="kaosgdd-faxmail-incoming-") as tmp_dir:
        pdf_path = Path(tmp_dir) / f"{source.stem}.pdf"
        try:
            convert_tiff_to_pdf(source, pdf_path)
        except RuntimeError as exc:
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
        send_message(config, message)
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

    config["smtp_port"] = int(os.environ.get("FAXMAIL_SMTP_PORT", "587"))
    config["smtp_user"] = os.environ.get("FAXMAIL_SMTP_USER", "").strip()
    config["smtp_password"] = os.environ.get("FAXMAIL_SMTP_PASSWORD", "")
    config["smtp_starttls"] = env_bool("FAXMAIL_SMTP_STARTTLS", default=True)
    config["smtp_ssl"] = env_bool("FAXMAIL_SMTP_SSL", default=False)
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
