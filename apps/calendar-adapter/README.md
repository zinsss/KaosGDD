# Calendar Adapter

KaosGDD adapter for Radicale calendar and task collections.

The browser shell calls:

```text
GET /api/calendar/bootstrap
POST /api/calendar/tasks
```

The adapter talks to Radicale through CalDAV HTTP. It does not read Radicale files or access databases directly.

`POST /api/calendar/tasks` creates a VTODO in the selected Radicale task collection. The mobile shell refreshes from `GET /api/calendar/bootstrap` after a successful write, so the UI shows Radicale as the source of truth.

## Environment

```text
RADICALE_INTERNAL_URL=http://100.94.208.16:5232
RADICALE_USERNAME=
RADICALE_PASSWORD=
KAOSGDD_ADAPTER_TIMEOUT_SECONDS=30
```

Credentials should come from `/srv/kaos/secrets/kaosgdd-adapters.env` in production.

## Production Behavior

If credentials are missing or Radicale has no discoverable collections, the API returns a non-live payload and the mobile shell keeps its local preview data.

If Radicale is live but a task write fails, the mobile shell reports the failure instead of silently saving a local-only task.
