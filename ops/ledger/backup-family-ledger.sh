#!/usr/bin/env bash
set -euo pipefail

BACKUP_ROOT="${LEDGER_HOST_BACKUP_ROOT:-/srv/kaos/backups/kaosgdd/ledger}"
DATABASE_CONTAINER="${LEDGER_DATABASE_CONTAINER:-kaosgdd-brain-database}"
DATABASE_NAME="${POSTGRES_DB:-kaosgdd_brain}"
DATABASE_USER="${POSTGRES_USER:-kaosgdd_brain}"
RETENTION_DAYS="${LEDGER_PGDUMP_RETENTION_DAYS:-90}"
DOCKER_BIN="${DOCKER_BIN:-/usr/bin/docker}"
STAMP="$(date +%F)"
TARGET_DIR="${BACKUP_ROOT}/postgres/daily"
TARGET="${TARGET_DIR}/${STAMP}.dump"
TEMP="${TARGET}.tmp"

install -d -m 0700 "${TARGET_DIR}"
trap 'rm -f "${TEMP}"' EXIT

"${DOCKER_BIN}" exec "${DATABASE_CONTAINER}" \
  pg_dump -U "${DATABASE_USER}" -d "${DATABASE_NAME}" -Fc >"${TEMP}"

test -s "${TEMP}"
mv -f "${TEMP}" "${TARGET}"
sha256sum "${TARGET}" >"${TARGET}.sha256"

find "${TARGET_DIR}" -type f -name '*.dump' -mtime "+${RETENTION_DAYS}" -delete
find "${TARGET_DIR}" -type f -name '*.dump.sha256' -mtime "+${RETENTION_DAYS}" -delete
