# Calendar Adapter

KaosGDD adapter for Radicale calendar and task collections.

The browser shell calls:

```text
GET /api/calendar/bootstrap
POST /api/calendar/events
PUT /api/calendar/events
DELETE /api/calendar/events
POST /api/calendar/tasks
PUT /api/calendar/tasks
DELETE /api/calendar/tasks
GET /internal/system/caregiver?month=YYYY-MM
PUT /internal/system/caregiver/day
PUT /internal/system/caregiver/settings
```

The adapter talks to Radicale through CalDAV HTTP. It does not read Radicale files or access databases directly.

`POST /api/calendar/events` creates a VEVENT in the selected Radicale calendar collection.

`PUT /api/calendar/events` updates a VEVENT by UID. It preserves properties that the KaosGDD form does not own, preserves unsupported custom recurrence/alarm data, increments `SEQUENCE`, and uses the Radicale ETag as an `If-Match` write guard. Multi-component recurrence resources must be edited in a native calendar client.

`DELETE /api/calendar/events` deletes the matching Radicale resource. A recurring series stored in that resource is deleted as a series.

`POST /api/calendar/tasks` creates a VTODO in the selected Radicale task collection. The mobile shell refreshes from `GET /api/calendar/bootstrap` after a successful write, so the UI shows Radicale as the source of truth.

`PUT /api/calendar/tasks` updates an existing VTODO by UID while preserving the original task UID, created timestamp, and completion status. Updates use the Radicale ETag as an `If-Match` write guard.

`DELETE /api/calendar/tasks` deletes an existing VTODO by UID.

Caregiver internal routes use deterministic VJOURNAL resources in the
`Kaos_Caregiver` system collection. Daily records store session ranges and
optional extras. Monthly settings store hourly wage and transport fee. These
routes are internal adapter contracts and must not be exposed directly by
Caddy.

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

## System Logs

The adapter exposes a backend-only system journal endpoint on the internal adapter port:

```text
GET  /internal/system/logs
POST /internal/system/logs
```

This path is intentionally not under `/api/calendar/*`, so it is not routed by the public portal edge. It writes `VJOURNAL` entries to the `Kaos_Logs` collection owned by the `kaos` Radicale account.

Example payload:

```json
{
  "summary": "Radicale portal profiles deployed",
  "memo": "kaosgdd.net reads zin + family; family.kaosgdd.net reads wife + family.",
  "category": "deploy"
}
```

## Weather History

Daily weather history uses the same backend-only pattern:

```text
GET  /internal/system/weather
POST /internal/system/weather
```

It writes one deterministic `VJOURNAL` per city/date to `Kaos_Weather`. Re-posting the same city/date updates the same entry instead of creating duplicates.

Supported city keys:

```text
pohang
daegu
yeongdeok
```

Example payload:

```json
{
  "city": "pohang",
  "date": "2026-07-26",
  "minTemp": 21,
  "maxTemp": 32,
  "glyph": "sun",
  "condition": "clear",
  "source": "manual"
}
```

The browser calendar reads month weather through a public read-only endpoint:

```text
GET /api/weather/month?city=pohang&start=2026-06-28&end=2026-08-08
```

The month endpoint merges:

- saved `Kaos_Weather` history for past dates
- live Open-Meteo forecast for today/future dates

Past history returns a daily summary only. Today/future forecast may include dayparts for selected-day detail.

Weather history is saved lazily:

- today/future forecast is never written to `Kaos_Weather`
- missing past dates are fetched from Open-Meteo archive when a month is viewed
- existing `Kaos_Weather` entries are not overwritten automatically

## Production Behavior

If credentials are missing or Radicale has no discoverable collections, the API returns a non-live payload and the mobile shell keeps its local preview data.

If Radicale is live but a task write fails, the mobile shell reports the failure instead of silently saving a local-only task.
