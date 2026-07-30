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

Brain is not routed through Caddy while it is in shadow mode.

## Current Routes

Brain should keep existing browser routes stable:

```text
GET /health
GET /api/brain/status
GET /api/calendar/bootstrap
GET /api/weather/month
```

Later routes may include:

```text
GET /api/brain/status
GET /api/weather/month
POST /api/weather/current
GET /api/caregiver/month
PUT /api/caregiver/day
```

## Safety

Brain may restart independently from:

- Caddy
- cloudflared
- KaosPACS
- Radicale
- Paperless
- Wiki.js
- KaosSupplies
- KaosFaxMail or the legacy fax bridge

Brain must not:

- read service databases directly
- read or modify PACS storage
- write user Radicale data outside explicit adapter calls
- write current-location weather history by default

## Migration Checklist

1. Keep Brain running beside the adapter on internal port `8092`. Complete.
2. Compare `/api/calendar/bootstrap` and `/api/weather/month` payloads for the main and family profiles. Complete.
3. Add write endpoint parity with tests.
4. Point portal proxy to Brain.
5. Keep the old adapter available for rollback.
6. Remove old adapter only after stable testing.

Run parity checks from the repository:

```bash
python3 apps/brain/scripts/compare_adapter.py
```

Build tagged Brain images on the Control Center. Production Compose references
the image tag and must not build application images on the production server
during normal deployments.
