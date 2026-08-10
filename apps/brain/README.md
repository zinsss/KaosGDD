# KaosGDD Brain

KaosGDD Brain is the small backend for KaosGDD v2 orchestration.

It is not a replacement for Radicale, Paperless, Wiki.js, HylaFAX, or PACS. It exists for logic that the static shell cannot do safely by itself.

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
- temporary PDF intake, preview, expiry, and explicit Paperless handoff
- incoming fax notification polling over the HylaFAX receive queue
- idempotent Telegram archival of confirmed incoming and outgoing fax documents
- personal Memos archival to Telegram with in-place edit tracking and deletion preservation
- audited Family medical association ledger storage and XLSX recovery backups
- service health/status aggregation

Brain does not own:

- normal user calendar events
- normal user tasks
- authoritative document storage
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

Brain `0.7.0` is the side-by-side runtime:

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
- main-profile temporary PDF queue and explicit Paperless consume-folder handoff
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

## Temporary Documents

Brain accepts PDF output from RHWP, Stirling-PDF, iOS Shortcuts, and the portal.
These files are temporary workflow artifacts, not a second document archive.

```text
POST   /api/documents?filename=result.pdf&source=hwp
GET    /api/documents
GET    /api/documents/{id}/content
POST   /api/documents/{id}/paperless
DELETE /api/documents/{id}
```

Uploads use a raw `application/pdf` request body. Brain validates the PDF
signature, stores it under a random name, records its size and SHA-256 digest,
and exposes byte-range preview for Safari and other PDF viewers. A document is
copied atomically into Paperless's consume directory only after the explicit
Paperless action. Sending it does not delete the temporary preview immediately.

Available files expire after 48 hours by default. Submitted files expire after
24 hours. The cleanup worker also removes abandoned partial uploads. Paperless
remains the authoritative long-term document owner.

## Fax Notifications

Incoming fax remains owned by HylaFAX. Brain watches the HylaFAX receive queue,
sends a pushed Telegram message, and archives the converted PDF to Telegram.

```text
HylaFAX recvq mounted read-only at /integrations/hylafax
Brain polls recvq/fax*.tif
Brain posts a short message to the Telegram Notifications topic
Brain archives the fax PDF to the Telegram Fax topic
```

The worker is controlled by:

```text
FAX_NOTIFY_ENABLED=true
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true
```

The first run marks existing receive-queue files as already seen by default, so
deploying the worker does not spam notifications for old faxes. Successful fax
receipt notices go to `Notifications`; transmission failures go to
`System Alerts`.

Telegram uses one private supergroup and explicit numeric topic IDs:

```env
TELEGRAM_BOT_TOKEN=
TELEGRAM_SUPERGROUP_CHAT_ID=
TELEGRAM_TOPIC_NOTIFICATIONS_ID=
TELEGRAM_TOPIC_SYSTEM_ALERTS_ID=
```

Inbound bot actions are group-only. Brain accepts an update only when both the
numeric chat ID matches `TELEGRAM_SUPERGROUP_CHAT_ID` and Telegram reports the
chat type as `supergroup`; private chats and all other groups are ignored.

Telegram topic notification settings control device delivery. Brain sends
normal and former device-specific channels to `Notifications`, and the
`system` channel to `System Alerts`. Brain does not maintain per-device
notification credentials.

## Personal Memos Archive

Brain polls the current Memos v1 API with the encrypted personal relay token and
copies personal memos into the private Telegram `Memos` topic. Memos remains the
source of truth. Family memos are intentionally excluded.

The archive state contains only memo resource names, content hashes, update
timestamps, and Telegram message IDs. It does not duplicate memo bodies. New
memos create silent Telegram messages, edits update the same messages, and a
memo deleted from Memos leaves its archived messages intact with a separate
deletion marker. Long memo content is split without truncation. Attachment
names are recorded; binary attachment export is deferred until its download
contract is verified against the live Memos API.

The existing Telegram update consumer also enforces the Memos topic as
read-only by deleting non-bot messages. Do not start a second `getUpdates`
worker for the same bot token because Telegram update offsets are shared.

```env
MEMOS_TELEGRAM_ARCHIVE_ENABLED=true
MEMOS_TELEGRAM_ARCHIVE_STATE_PATH=/data/memos/telegram-archive.json
MEMOS_TELEGRAM_ARCHIVE_POLL_SECONDS=60
TELEGRAM_MEMOS_TOPIC_READ_ONLY=true
```

## Mail Notifications

Brain polls the Naver `각종공문`, `세무사`, and descendant folders read-only
without storing message bodies. Fax does not use IMAP: outgoing PDF requests
arrive directly through the configured Telegram `Fax` topic.

The worker records only UIDVALIDITY, last processed UID, folder display name,
and aggregate runtime status under `/data/mail`. Existing messages establish the
first checkpoint and do not notify. New matching messages are published to both
the iOS and desktop audience topics.

Keep Naver disabled until its IMAP/app password has been entered in the
protected Brain environment.

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
