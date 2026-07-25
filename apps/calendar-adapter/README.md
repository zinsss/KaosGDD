# Calendar Adapter

KaosGDD adapter for Radicale calendar and task collections.

The browser shell calls:

```text
GET /api/calendar/bootstrap
POST /api/calendar/events
POST /api/calendar/tasks
PUT /api/calendar/tasks
```

The adapter talks to Radicale through CalDAV HTTP. It does not read Radicale files or access databases directly.

`POST /api/calendar/events` creates a VEVENT in the selected Radicale calendar collection.

`POST /api/calendar/tasks` creates a VTODO in the selected Radicale task collection. The mobile shell refreshes from `GET /api/calendar/bootstrap` after a successful write, so the UI shows Radicale as the source of truth.

`PUT /api/calendar/tasks` updates an existing VTODO by UID while preserving the original task UID, created timestamp, and completion status.

## Environment

```text
RADICALE_INTERNAL_URL=http://100.94.208.16:5232
RADICALE_USERNAME=
RADICALE_PASSWORD=
RADICALE_FAMILY_USERNAME=
RADICALE_FAMILY_PASSWORD=
RADICALE_WIFE_USERNAME=
RADICALE_WIFE_PASSWORD=
KAOSGDD_ADAPTER_TIMEOUT_SECONDS=30
```

Credentials should come from `/srv/kaos/secrets/kaosgdd-adapters.env` in production.

## Portal Profiles

The adapter chooses which Radicale accounts are visible from the request hostname:

```text
kaosgdd.net
  reads/writes: zin, family

family.kaosgdd.net
  reads/writes: wife, family
```

The system/brain Radicale account is not exposed through the browser calendar API.
Human accounts are discovered by account and component type, not fixed collection names.

## Production Behavior

If credentials are missing or Radicale has no discoverable collections, the API returns a non-live payload and the mobile shell keeps its local preview data.

If Radicale is live but a task write fails, the mobile shell reports the failure instead of silently saving a local-only task.
