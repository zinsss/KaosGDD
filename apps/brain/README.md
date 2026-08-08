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
- repeating-task definitions and one-at-a-time VTODO generation
- cross-device event preset storage with personal and Family scopes
- incoming fax notification polling over the HylaFAX receive queue
- audited Family medical association ledger storage and XLSX recovery backups
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

Brain `0.5.1` is the side-by-side runtime:

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
- family-only ledger CRUD, XLSX export, and manual backup under `/api/ledger`
- strict Rouny time-range validation while allowing intentional overlaps
- strict method/path allowlisting
- supplies API backed by Radicale `Kaos_Supplies`
- repeating-task CRUD and scheduler APIs backed by standard Radicale VTODOs
- event preset CRUD shared by the main and Family portal UIs
- Google Korea calendar sync into the existing Family CalDAV collection, with manual public-holiday classification
- Caddy routes for `/api/caregiver/*` and `/api/rouny/*` on `family.kaosgdd.net`
- Caddy route for `/api/supplies*` on `kaosgdd.net`

PostgreSQL owns Brain configuration, Rouny timetable templates, supplies
preset/recent history, and the Family medical association ledger. Radicale remains authoritative for events, tasks, weather
journals, caregiver journals, and the supplies buy-list collection.

Repeating task definitions live in Brain PostgreSQL. Brain generates one normal
VTODO at a time and watches its UID in Radicale. Completion or deletion advances
the fixed daily, weekly, monthly, or yearly schedule. Generated tasks contain no
Kaos-only calendar metadata, so they remain compatible with iOS Reminders.

Event presets also live in Brain PostgreSQL. Main personal presets belong to
ZiN. The Family portal creates and sees only shared Family presets, which remain
visible from both portals. Presets only store template fields; events created
from them remain normal Radicale VEVENTs.

Google Korea holiday and observance entries remain normal all-day VEVENTs in
the Family collection. Brain adds standard `CATEGORIES` markers so the portal
can distinguish red public holidays from dim informational observances. Manual
classification survives later source syncs, and generated entries are read-only
through normal event editing routes.


## Fax Notifications

Incoming fax remains owned by HylaFAX and the hosted mailbox. Brain only watches
the HylaFAX receive queue and sends a push notification through ntfy when a new
TIFF appears.

```text
HylaFAX recvq mounted read-only at /integrations/hylafax
Brain polls recvq/fax*.tif
Brain posts a short message to ntfy
Roundcube remains the fax inbox
```

The worker is controlled by:

```text
FAX_NOTIFY_ENABLED=true
NTFY_URL=http://ntfy
NTFY_TOPIC_IOS=kaosgdd-ios
NTFY_TOPIC_DESKTOP=kaosgdd-desktop
NTFY_TOPIC_SYSTEM=kaosgdd-system
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true
```

The first run marks existing receive-queue files as already seen by default, so
deploying the worker does not spam notifications for old faxes. Successful fax
receipt notices go to both audience topics. Mailbox-delivery failures use the
system topic. Future calendar and task reminders are desktop-only.

## Mail Notifications

Brain can poll two read-only IMAP sources without storing message bodies:

- Naver: `각종공문`, `세무사`, and every descendant folder under either root
- Gmail: `INBOX`, filtered to the configured KaosGDD fax aliases

The worker records only UIDVALIDITY, last processed UID, folder display name,
and aggregate runtime status under `/data/mail`. Existing messages establish the
first checkpoint and do not notify. New matching messages are published to both
the iOS and desktop audience topics.

Each account has an independent enable flag and password. Keep an account
disabled until its IMAP/app password has been entered in the protected Brain
environment.

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
