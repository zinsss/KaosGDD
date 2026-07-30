# KaosGDD Brain

KaosGDD Brain is the small backend for KaosGDD v2 orchestration.

It is not a replacement for Radicale, Paperless, Wiki.js, KaosSupplies, KaosFaxMail, or PACS. It exists for logic that the static shell cannot do safely by itself.

## Scope

Brain owns:

- adapter APIs used by the KaosGDD shell
- Radicale CalDAV/CardDAV access
- task and calendar normalization
- Apple Reminders ordering compatibility
- generated calendar overlays, such as Market Saturday and Claim Day
- weather fetch and generated weather history journals
- caregiver journal normalization and monthly review calculations
- service health/status aggregation

Brain does not own:

- normal user calendar events
- normal user tasks
- document storage
- notes or knowledge storage
- passwords
- PACS data
- service databases owned by other apps

## Current First Piece

The existing `apps/calendar-adapter` is the first live slice of Brain.

It should be folded into this app without changing the public browser contract:

```text
GET /api/calendar/bootstrap
```

The migration should keep production stable:

1. keep the current adapter running
2. build equivalent Brain endpoint locally
3. deploy Brain beside the current adapter
4. switch the portal proxy only after endpoint parity is verified
5. remove the old adapter stack only after the Brain route is stable

Brain `0.1.0-shadow` is the first side-by-side runtime:

- private PostgreSQL database with migration tracking
- `GET /health`
- `GET /api/brain/status`
- read-only proxy parity for `GET /api/calendar/bootstrap`
- read-only proxy parity for `GET /api/weather/month`
- no public Caddy route
- no calendar/task writes

PostgreSQL owns only Brain configuration. Radicale remains authoritative for events, tasks, weather journals, and future caregiver journals.

## Proposed Layout

```text
apps/brain/
  api/
  adapters/
    radicale/
    weather/
  services/
    calendar/
    caregiver/
    system_calendar/
    weather/
  models/
  scripts/
  tests/
```

## Production Target

```text
/srv/kaos/stacks/platform/kaosgdd/brain/compose.yaml
/srv/kaos/data/kaosgdd/brain/
/srv/kaos/secrets/kaosgdd-brain.env
```

Brain should remain independently restartable from the static portal.
Build release images on the Control Center and deploy the tagged image to
production. The production Compose file does not contain a build context.

Production shadow port:

```text
http://100.94.208.16:8092
```

The PostgreSQL service has no host port.

## Local Tests

```bash
python3 -m unittest discover -s apps/brain/tests -v
docker build -t kaosgdd-brain:test apps/brain
```

## Parity Check

```bash
python3 apps/brain/scripts/compare_adapter.py
```

Additional read paths can be compared explicitly:

```bash
python3 apps/brain/scripts/compare_adapter.py \
  --path /api/calendar/bootstrap \
  --path '/api/weather/month?city=pohang&start=2026-07-01&end=2026-07-31'
```

## Database Backup

The PostgreSQL bind mount is included in the Kaos backup manifest through `/srv/kaos/data/kaosgdd`. Once Synology backup jobs are enabled, add a logical dump:

```bash
docker exec kaosgdd-brain-database \
  pg_dump -U kaosgdd_brain -d kaosgdd_brain -Fc
```

Do not treat a live raw PostgreSQL data-directory copy as the only database backup.
