# Calendar Adapter

Read-only KaosGDD adapter for Radicale.

The browser shell calls:

```text
GET /api/calendar/bootstrap
```

The adapter talks to Radicale through CalDAV HTTP. It does not read Radicale files, access databases, or write calendar/task data.

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
