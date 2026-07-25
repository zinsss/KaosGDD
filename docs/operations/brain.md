# Brain Operations

KaosGDD Brain is not live yet.

The current live first slice is still:

```text
/srv/kaos/stacks/platform/kaosgdd/calendar-adapter/compose.yaml
/srv/kaos/data/kaosgdd/calendar-adapter/server.py
```

## Target Production Paths

```text
/srv/kaos/stacks/platform/kaosgdd/brain/compose.yaml
/srv/kaos/data/kaosgdd/brain/
/srv/kaos/secrets/kaosgdd-adapters.env
```

## Target Routes

Brain should keep existing browser routes stable:

```text
GET /api/calendar/bootstrap
GET /api/weather
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

1. Build Brain endpoint parity with the current calendar adapter.
2. Run Brain beside the adapter on a new internal port.
3. Compare `/api/calendar/bootstrap` payloads.
4. Point portal proxy to Brain.
5. Keep the old adapter available for rollback.
6. Remove old adapter only after stable testing.
