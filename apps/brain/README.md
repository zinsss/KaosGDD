# KaosGDD Brain

KaosGDD Brain is the small backend for KaosGDD v2 orchestration.

It is not a replacement for Radicale, Paperless, Wiki.js, KaosFaxMail, or PACS. It exists for logic that the static shell cannot do safely by itself.

## Scope

Brain owns:

- adapter APIs used by the KaosGDD shell
- Radicale CalDAV/CardDAV access
- task and calendar normalization
- Apple Reminders ordering compatibility
- generated calendar overlays, such as Market Saturday and Claim Day
- weather fetch and generated weather history journals
- caregiver journal normalization and monthly review calculations
- supplies buy-list compatibility behavior over a Radicale task collection
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

Brain `0.4.2` is the side-by-side runtime:

- private PostgreSQL database with migration tracking
- `GET /health`
- `GET /api/brain/status`
- proxy parity for `GET /api/calendar/bootstrap`
- proxy parity for `GET /api/weather/month`
- write-through parity for event and task `POST`, `PUT`, and `DELETE`
- family-only `GET /api/caregiver/month`
- family-only `PUT /api/caregiver/day`
- family-only `DELETE /api/caregiver/day`
- family-only `PUT /api/caregiver/settings`
- family-only `GET /api/rouny/templates`
- family-only revision-checked `PUT /api/rouny/templates`
- strict Rouny time-range validation while allowing intentional overlaps
- strict method/path allowlisting
- supplies API backed by Radicale `Kaos_Supplies`
- Caddy routes for `/api/caregiver/*` and `/api/rouny/*` on `family.kaosgdd.net`
- Caddy route for `/api/supplies*` on `kaosgdd.net`

PostgreSQL owns Brain configuration, Rouny timetable templates, and supplies
preset/recent history. Radicale remains authoritative for events, tasks, weather
journals, caregiver journals, and the supplies buy-list collection.

## Supplies

Supplies should move into KaosGDD as a dedicated buy-list UI backed by Brain.
The browser should not call the old KaosSupplies service directly, and no
`supplies.kaosgdd.net` entry point is required for the new path.

The compatibility behavior comes from the existing KaosSupplies service:

- active supplies are listed oldest first by created time
- completed supplies are listed newest first by completion time
- titles are cleaned with whitespace collapsed
- active titles are deduplicated by lowercased collapsed title
- completed items do not block adding the same title again
- presets are recent supply names, capped to 15, newest first
- `$$ item` capture creates a supply and returns `created_types: ["supply"]`

Radicale stores each supply as a `VTODO` in the `Kaos_Supplies` task collection.
Brain stores only the preset/recent metadata that Radicale does not model cleanly.

Rouny templates are stored as one atomic document for the Family portal. Each
write includes the last server revision; stale writes receive `409` and both
copies remain available for explicit conflict resolution in the portal. The
browser keeps a local cache so an unavailable Brain does not erase a timetable.

The monthly caregiver review follows the legacy KaosGDD calculation:

```text
base pay = total session minutes / 60 * hourly wage
total payout = base pay + daily extras + monthly transport fee
```

Brain performs the calculation in integer minutes. If the selected month has no
wage settings, it uses the latest earlier monthly setting. The shell only
renders the result.

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

Compare all write error contracts without creating records:

```bash
python3 apps/brain/scripts/compare_writes.py
```

Run a reversible create, update, read, and delete cycle:

```bash
python3 apps/brain/scripts/verify_write_cycle.py --host kaosgdd.net
python3 apps/brain/scripts/verify_write_cycle.py --host family.kaosgdd.net
```

## Database Backup

The PostgreSQL bind mount is included in the Kaos backup manifest through `/srv/kaos/data/kaosgdd`. Once Synology backup jobs are enabled, add a logical dump:

```bash
docker exec kaosgdd-brain-database \
  pg_dump -U kaosgdd_brain -d kaosgdd_brain -Fc
```

Do not treat a live raw PostgreSQL data-directory copy as the only database backup.
