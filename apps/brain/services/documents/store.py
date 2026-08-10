import hashlib
import os
import re
import shutil
import threading
import time
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

from models.database import connect


ALLOWED_SOURCES = {"hwp", "stirling", "shortcut", "upload"}
PDF_CONTENT_TYPES = {"application/pdf", "application/octet-stream"}
SELECT_COLUMNS = """
    id, profile, source, original_filename, stored_filename, content_type,
    size_bytes, sha256, status, paperless_filename, created_at, updated_at,
    expires_at, submitted_at
"""


def temp_root():
    return Path(os.environ.get("DOCUMENT_TEMP_ROOT", "/data/documents/temp"))


def paperless_consume_root():
    return Path(os.environ.get("PAPERLESS_CONSUME_ROOT", "/integrations/paperless-consume"))


def max_upload_bytes():
    return int(os.environ.get("DOCUMENT_MAX_UPLOAD_MB", "100")) * 1024 * 1024


def storage_status():
    temporary = temp_root()
    consume = paperless_consume_root()
    return {
        "ok": temporary.is_dir() and os.access(temporary, os.W_OK),
        "temporaryWritable": temporary.is_dir() and os.access(temporary, os.W_OK),
        "paperlessHandoffWritable": consume.is_dir() and os.access(consume, os.W_OK),
        "maxUploadMB": max_upload_bytes() // (1024 * 1024),
    }


def retention_hours(status="available"):
    key = "DOCUMENT_SUBMITTED_RETENTION_HOURS" if status == "submitted" else "DOCUMENT_RETENTION_HOURS"
    fallback = "24" if status == "submitted" else "48"
    return max(1, int(os.environ.get(key, fallback)))


def clean_filename(value):
    name = Path(str(value or "document.pdf").replace("\\", "/")).name
    name = unicodedata.normalize("NFC", name).strip().replace("\x00", "")
    name = re.sub(r"[\r\n\t]+", " ", name)
    name = re.sub(r"\s+", " ", name)
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    stem = name[:-4].strip(" .") or "document"
    return f"{stem[:180]}.pdf"


def validate_source(value):
    source = str(value or "upload").strip().lower()
    if source not in ALLOWED_SOURCES:
        raise ValueError("invalid_document_source")
    return source


def validate_upload(content_type, content_length):
    media_type = str(content_type or "").split(";", 1)[0].strip().lower()
    if media_type not in PDF_CONTENT_TYPES:
        raise ValueError("pdf_required")
    try:
        length = int(content_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("document_length_required") from exc
    if length <= 0:
        raise ValueError("empty_document")
    if length > max_upload_bytes():
        raise ValueError("document_too_large")
    return length


def _row_to_item(row):
    if not row:
        return None
    values = list(row)
    return {
        "id": values[0],
        "profile": values[1],
        "source": values[2],
        "original_filename": values[3],
        "stored_filename": values[4],
        "content_type": values[5],
        "size_bytes": values[6],
        "sha256": values[7],
        "status": values[8],
        "paperless_filename": values[9],
        "created_at": values[10],
        "updated_at": values[11],
        "expires_at": values[12],
        "submitted_at": values[13],
    }


def _iso(value):
    return value.isoformat() if value is not None else ""


def public_item(item):
    return {
        "id": item["id"],
        "source": item["source"],
        "filename": item["original_filename"],
        "contentType": item["content_type"],
        "sizeBytes": int(item["size_bytes"]),
        "sha256": item["sha256"],
        "status": item["status"],
        "paperlessFilename": item["paperless_filename"] or "",
        "createdAt": _iso(item["created_at"]),
        "expiresAt": _iso(item["expires_at"]),
        "submittedAt": _iso(item["submitted_at"]),
        "contentUrl": f"/api/documents/{item['id']}/content",
    }


def list_documents(profile="main"):
    cleanup_expired()
    with connect() as connection:
        rows = connection.execute(
            f"""
            SELECT {SELECT_COLUMNS}
            FROM document_queue
            WHERE profile = %s
            ORDER BY created_at DESC, id
            """,
            (profile,),
        ).fetchall()
    return {"ok": True, "items": [public_item(_row_to_item(row)) for row in rows]}


def get_document(document_id, profile="main"):
    with connect() as connection:
        row = connection.execute(
            f"SELECT {SELECT_COLUMNS} FROM document_queue WHERE id = %s AND profile = %s",
            (str(document_id or ""), profile),
        ).fetchone()
    if not row:
        raise ValueError("document_not_found")
    item = _row_to_item(row)
    path = temp_root() / item["stored_filename"]
    if not path.is_file():
        raise ValueError("document_file_missing")
    return item, path


def store_document(stream, content_length, filename, source="upload", profile="main"):
    expected = validate_upload("application/pdf", content_length)
    original_filename = clean_filename(filename)
    source = validate_source(source)
    document_id = str(uuid.uuid4())
    stored_filename = f"{document_id}.pdf"
    root = temp_root()
    root.mkdir(parents=True, exist_ok=True)
    partial = root / f".{stored_filename}.part"
    final = root / stored_filename
    digest = hashlib.sha256()
    written = 0
    try:
        with partial.open("xb") as output:
            while written < expected:
                chunk = stream.read(min(1024 * 1024, expected - written))
                if not chunk:
                    break
                output.write(chunk)
                digest.update(chunk)
                written += len(chunk)
            output.flush()
            os.fsync(output.fileno())
        if written != expected:
            raise ValueError("incomplete_document")
        with partial.open("rb") as uploaded:
            if uploaded.read(5) != b"%PDF-":
                raise ValueError("invalid_pdf_signature")
        os.replace(partial, final)
        with connect() as connection:
            row = connection.execute(
                """
                INSERT INTO document_queue (
                    id, profile, source, original_filename, stored_filename,
                    content_type, size_bytes, sha256, expires_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, 'application/pdf', %s, %s,
                    now() + (%s * interval '1 hour')
                )
                RETURNING id
                """,
                (
                    document_id,
                    profile,
                    source,
                    original_filename,
                    stored_filename,
                    written,
                    digest.hexdigest(),
                    retention_hours("available"),
                ),
            ).fetchone()
        if not row:
            raise RuntimeError("document_create_failed")
    except Exception:
        partial.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
        raise
    item, _ = get_document(document_id, profile)
    return public_item(item)


def submit_to_paperless(document_id, profile="main"):
    item, source_path = get_document(document_id, profile)
    if item["status"] == "submitted":
        raise ValueError("document_already_submitted")
    consume_root = paperless_consume_root()
    consume_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target_name = clean_filename(f"kaos-{timestamp}-{item['id'][:8]}-{item['original_filename']}")
    partial = consume_root / f".{target_name}.part"
    target = consume_root / target_name
    if target.exists() or partial.exists():
        raise RuntimeError("paperless_target_conflict")
    try:
        with source_path.open("rb") as source, partial.open("xb") as destination:
            shutil.copyfileobj(source, destination, length=1024 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(partial, target)
    except PermissionError as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError("paperless_consume_unavailable") from exc
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise RuntimeError("paperless_handoff_failed") from exc
    try:
        with connect() as connection:
            row = connection.execute(
                """
                UPDATE document_queue
                SET status = 'submitted',
                    paperless_filename = %s,
                    submitted_at = now(),
                    updated_at = now(),
                    expires_at = now() + (%s * interval '1 hour')
                WHERE id = %s AND profile = %s
                RETURNING id
                """,
                (target_name, retention_hours("submitted"), item["id"], profile),
            ).fetchone()
        if not row:
            raise RuntimeError("document_submit_state_failed")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    updated, _ = get_document(item["id"], profile)
    return public_item(updated)


def delete_document(document_id, profile="main"):
    item, path = get_document(document_id, profile)
    path.unlink(missing_ok=True)
    with connect() as connection:
        connection.execute("DELETE FROM document_queue WHERE id = %s AND profile = %s", (item["id"], profile))
    return {"ok": True, "id": item["id"]}


def cleanup_expired():
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, stored_filename FROM document_queue WHERE expires_at <= now()"
        ).fetchall()
        for _, stored_filename in rows:
            (temp_root() / stored_filename).unlink(missing_ok=True)
        if rows:
            connection.execute(
                "DELETE FROM document_queue WHERE id = ANY(%s)",
                ([row[0] for row in rows],),
            )
    root = temp_root()
    if root.is_dir():
        cutoff = time.time() - 3600
        for partial in root.glob(".*.part"):
            try:
                if partial.stat().st_mtime < cutoff:
                    partial.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
    return len(rows)


def start_cleanup_scheduler():
    interval = max(60, int(os.environ.get("DOCUMENT_CLEANUP_INTERVAL_SECONDS", "900")))

    def run():
        while True:
            try:
                cleanup_expired()
            except Exception as exc:
                print(f"Document cleanup failed: {type(exc).__name__}", flush=True)
            time.sleep(interval)

    thread = threading.Thread(target=run, name="document-cleanup", daemon=True)
    thread.start()
    return thread
