# Family Ledger Operations

## Production Paths

```text
/srv/kaos/backups/kaosgdd/ledger/latest.xlsx
/srv/kaos/backups/kaosgdd/ledger/daily/
/srv/kaos/backups/kaosgdd/ledger/monthly/
/srv/kaos/backups/kaosgdd/ledger/manual/
/srv/kaos/backups/kaosgdd/ledger/postgres/daily/
/srv/kaos/backups/kaosgdd/ledger/migration/
```

The Brain container mounts this root at `/data/ledger/backups`. Synology should
copy the host root after the NAS backup target is ready.

Production runs `/srv/kaos/scripts/backup-family-ledger.sh` at 03:35 through the
`zin` user crontab. The repository also includes systemd service and timer units
for a later root-managed installation.

## Legacy Import

Keep the original workbook and its checksum under `migration/`. Validate before
writing:

```bash
docker exec kaosgdd-brain python -m services.ledger.import_xlsx \
  /data/ledger/backups/migration/maya-ledger-source.xlsx --dry-run
```

The report must show 195 entries and these balances:

```text
account: 1,370,000
cash: 3,460,400
gift: 850,000
```

Run the same command without `--dry-run` only while the ledger tables are empty.
The importer checks every source row's cached balances inside one database
transaction. Any mismatch aborts the entire import.

## Recovery Checks

Validate an XLSX by opening it with LibreOffice or Excel and comparing the `정보`
sheet balances to `GET /api/ledger`. Validate a database dump without restoring
over production:

```bash
pg_restore --list YYYY-MM-DD.dump >/dev/null
sha256sum --check YYYY-MM-DD.dump.sha256
```

Restore into a separate temporary database first. Never restore directly over the
live Brain database without a current dump and an explicit maintenance window.
