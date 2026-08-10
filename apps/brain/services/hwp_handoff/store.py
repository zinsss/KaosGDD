import json
import os
import re
import time
import unicodedata
import urllib.parse
import uuid
from pathlib import Path


CONTENT_TYPES = {
    ".hwp": "application/x-hwp",
    ".hwpx": "application/hwp+zip",
    ".hml": "application/xml",
}
ALLOWED_CONTENT_TYPES = {
    "application/octet-stream",
    "application/x-hwp",
    "application/haansofthwp",
    "application/hwp+zip",
    "application/zip",
    "application/xml",
    "text/xml",
}
TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def handoff_root():
    return Path(os.environ.get("HWP_HANDOFF_ROOT", "/data/documents/hwp-handoff"))


def max_upload_bytes():
    return int(os.environ.get("HWP_HANDOFF_MAX_UPLOAD_MB", "50")) * 1024 * 1024


def retention_seconds():
    return max(60, int(os.environ.get("HWP_HANDOFF_RETENTION_MINUTES", "30")) * 60)


def public_origin():
    return os.environ.get("KAOS_PUBLIC_ORIGIN", "https://kaosgdd.net").rstrip("/")


def clean_filename(value):
    name = Path(str(value or "document.hwp").replace("\\", "/")).name
    name = unicodedata.normalize("NFC", name).strip().replace("\x00", "")
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name)
    suffix = Path(name).suffix.lower()
    if suffix not in CONTENT_TYPES:
        raise ValueError("unsupported_hwp_extension")
    stem = name[: -len(suffix)].strip(" .") or "document"
    return f"{stem[:180]}{suffix}"


def validate_upload(content_type, content_length, filename):
    clean_name = clean_filename(filename)
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise ValueError("unsupported_hwp_content_type")
    try:
        length = int(content_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("handoff_length_required") from exc
    if length <= 0:
        raise ValueError("empty_handoff")
    if length > max_upload_bytes():
        raise ValueError("handoff_too_large")
    return clean_name, length


def _paths(token):
    if not TOKEN_PATTERN.fullmatch(str(token or "")):
        raise ValueError("handoff_not_found")
    root = handoff_root()
    return root / f"{token}.bin", root / f"{token}.json"


def _signature_matches(path, suffix):
    with path.open("rb") as source:
        head = source.read(512)
    if suffix == ".hwp":
        return head.startswith(bytes.fromhex("d0cf11e0a1b11ae1"))
    if suffix == ".hwpx":
        return head.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"))
    if suffix == ".hml":
        return head.lstrip(b"\xef\xbb\xbf\x00\t\r\n ").startswith(b"<")
    return False


def cleanup_expired(now=None):
    root = handoff_root()
    if not root.is_dir():
        return 0
    cutoff = float(now if now is not None else time.time()) - retention_seconds()
    removed = 0
    for metadata_path in root.glob("*.json"):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            created_at = float(metadata.get("createdAt", metadata_path.stat().st_mtime))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            created_at = metadata_path.stat().st_mtime
        if created_at >= cutoff:
            continue
        token = metadata_path.stem
        binary_path = root / f"{token}.bin"
        binary_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        removed += 1
    return removed


def store_handoff(stream, content_length, filename, content_type):
    clean_name, expected = validate_upload(content_type, content_length, filename)
    cleanup_expired()
    root = handoff_root()
    root.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    binary_path, metadata_path = _paths(token)
    partial_path = root / f".{token}.part"
    written = 0
    try:
        with partial_path.open("xb") as output:
            while written < expected:
                chunk = stream.read(min(1024 * 1024, expected - written))
                if not chunk:
                    break
                output.write(chunk)
                written += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if written != expected:
            raise ValueError("incomplete_handoff")
        suffix = Path(clean_name).suffix.lower()
        if not _signature_matches(partial_path, suffix):
            raise ValueError("invalid_hwp_signature")
        os.replace(partial_path, binary_path)
        created_at = time.time()
        metadata = {
            "token": token,
            "filename": clean_name,
            "contentType": CONTENT_TYPES[suffix],
            "sizeBytes": written,
            "createdAt": created_at,
            "expiresAt": created_at + retention_seconds(),
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    except Exception:
        partial_path.unlink(missing_ok=True)
        binary_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise

    content_path = f"/api/hwp-handoff/{token}/content"
    query = urllib.parse.urlencode({"url": content_path, "filename": clean_name})
    return {
        "filename": clean_name,
        "sizeBytes": written,
        "expiresAt": metadata["expiresAt"],
        "contentPath": content_path,
        "openUrl": f"{public_origin()}/rhwp/?{query}",
    }


def get_handoff(token):
    cleanup_expired()
    binary_path, metadata_path = _paths(token)
    if not binary_path.is_file() or not metadata_path.is_file():
        raise ValueError("handoff_not_found")
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("handoff_not_found") from exc
    if float(metadata.get("expiresAt", 0)) <= time.time():
        binary_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise ValueError("handoff_expired")
    return metadata, binary_path


def storage_status():
    root = handoff_root()
    return {
        "ok": root.is_dir() and os.access(root, os.W_OK),
        "maxUploadMB": max_upload_bytes() // (1024 * 1024),
        "retentionMinutes": retention_seconds() // 60,
    }

