# Brain Operations

KaosGDD Brain runs in shadow mode beside the calendar adapter.

The current live first slice is still:

```text
/srv/kaos/stacks/platform/kaosgdd/calendar-adapter/compose.yaml
/srv/kaos/data/kaosgdd/calendar-adapter/server.py
```

## Target Production Paths

```text
/srv/kaos/stacks/platform/kaosgdd/brain/compose.yaml
/srv/kaos/data/kaosgdd/brain/app/
/srv/kaos/data/kaosgdd/brain/postgres/
/srv/kaos/secrets/kaosgdd-brain.env
```

Runtime endpoints:

```text
Brain:      http://100.94.208.16:8092
PostgreSQL: private compose network only
```

Brain remains mostly shadowed. Caddy routes selected APIs, including
`/api/caregiver/*` and `/api/holidays*`, to Brain; calendar and weather stay on
the calendar adapter.

## Current Routes

Brain should keep existing browser routes stable:

```text
GET /health
GET /api/brain/status
GET /api/calendar/bootstrap
GET /api/weather/month
POST /api/calendar/events
PUT /api/calendar/events
DELETE /api/calendar/events
POST /api/calendar/tasks
PUT /api/calendar/tasks
DELETE /api/calendar/tasks
GET /api/caregiver/month
PUT /api/caregiver/day
DELETE /api/caregiver/day
PUT /api/caregiver/settings
GET /api/holidays
POST /api/holidays/sync
PUT /api/holidays/{uid}
```

Holiday sync is enabled with:

```text
HOLIDAY_SYNC_ENABLED=true
HOLIDAY_SYNC_INTERVAL_SECONDS=86400
GOOGLE_KOREA_HOLIDAY_ICAL_URL=https://calendar.google.com/calendar/ical/ko.south_korea%23holiday%40group.v.calendar.google.com/public/basic.ics
```

The calendar adapter must have `RADICALE_FAMILY_CALENDAR_NAME=Family`. The
first sync writes current- and next-year entries into that existing collection.

Generated Market Day and Claim Day events use:

```text
GENERATED_CALENDAR_SYNC_ENABLED=true
GENERATED_CALENDAR_SYNC_INTERVAL_SECONDS=86400
```

The adapter must also have
`RADICALE_GDD_CALENDAR_NAME=Kaos_Calendar`. Brain migration `008` stores only
the two display controls. Generated VEVENT content remains in Radicale.

Later routes may include:

```text
GET /api/brain/status
GET /api/weather/month
POST /api/weather/current
```

## Safety

Brain may restart independently from:

- Caddy
- cloudflared
- KaosPACS
- Radicale
- Paperless
- Wiki.js
- KaosSupplies legacy service, while the new supplies path is built
- KaosFaxMail or the legacy fax bridge

Brain must not:

- read service databases directly
- read or modify PACS storage
- write user Radicale data outside explicit adapter calls
- write current-location weather history by default

## Migration Checklist

1. Keep Brain running beside the adapter on internal port `8092`. Complete.
2. Compare `/api/calendar/bootstrap` and `/api/weather/month` payloads for the main and family profiles. Complete.
3. Add write endpoint parity with tests. Complete.
4. Route the family-only caregiver API to Brain. Complete.
5. Keep the old adapter available for rollback.
6. Point remaining portal API routes to Brain after stable testing.
7. Remove old adapter only after stable testing.

Run parity checks from the repository:

```bash
python3 apps/brain/scripts/compare_adapter.py
python3 apps/brain/scripts/compare_writes.py
python3 apps/brain/scripts/verify_write_cycle.py --host kaosgdd.net
python3 apps/brain/scripts/verify_write_cycle.py --host family.kaosgdd.net
```

Build tagged Brain images on the Control Center. Production Compose references
the image tag and must not build application images on the production server
during normal deployments.
