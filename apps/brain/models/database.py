import os
import time
from pathlib import Path


MIGRATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS brain_schema_migrations (
    version text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
)
"""


def connection_parameters():
    return {
        "host": os.environ.get("BRAIN_DB_HOST", "database"),
        "port": int(os.environ.get("BRAIN_DB_PORT", "5432")),
        "dbname": os.environ.get("POSTGRES_DB", "kaosgdd_brain"),
        "user": os.environ.get("POSTGRES_USER", "kaosgdd_brain"),
        "password": os.environ.get("POSTGRES_PASSWORD", ""),
        "connect_timeout": int(os.environ.get("BRAIN_DB_CONNECT_TIMEOUT_SECONDS", "5")),
    }


def connect():
    import psycopg

    return psycopg.connect(**connection_parameters())


def migration_files(directory):
    return sorted(Path(directory).glob("[0-9][0-9][0-9]_*.sql"))


def apply_migrations(directory):
    with connect() as connection:
        connection.execute(MIGRATION_TABLE_SQL)
        applied = {
            row[0]
            for row in connection.execute("SELECT version FROM brain_schema_migrations ORDER BY version").fetchall()
        }
        for path in migration_files(directory):
            version = path.stem.split("_", 1)[0]
            if version in applied:
                continue
            with connection.transaction():
                connection.execute(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO brain_schema_migrations (version) VALUES (%s)",
                    (version,),
                )


def wait_for_database_and_migrate(directory):
    attempts = int(os.environ.get("BRAIN_DB_STARTUP_ATTEMPTS", "20"))
    delay = float(os.environ.get("BRAIN_DB_STARTUP_DELAY_SECONDS", "1.5"))
    last_error = None
    for _ in range(attempts):
        try:
            apply_migrations(directory)
            return
        except Exception as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError("brain database did not become ready") from last_error


def database_status():
    try:
        with connect() as connection:
            row = connection.execute(
                """
                SELECT current_database(), current_user,
                       COALESCE((SELECT max(version) FROM brain_schema_migrations), '')
                """
            ).fetchone()
        return {
            "ok": True,
            "database": row[0],
            "user": row[1],
            "migration": row[2],
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": type(exc).__name__,
        }
