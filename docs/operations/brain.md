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
GET /api/documents
POST /api/documents
GET /api/documents/{id}/content
POST /api/documents/{id}/paperless
DELETE /api/documents/{id}
POST /api/hwp-handoff/upload
GET /api/hwp-handoff/{token}/content
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

## Telegram Memos Archive

Production stores archive metadata at:

```text
/srv/kaos/data/kaosgdd/brain/memos/telegram-archive.json
```

The file is mode `0600` and contains no memo bodies. Brain uses the personal
Memos relay PAT already encrypted in PostgreSQL, paginates
`GET /api/v1/memos`, and accepts only `creator == users/$MEMOS_PERSONAL_USERNAME`.
It never reads or archives the Family profile.

Expected status is available under:

```text
GET /api/brain/status
upstreams.memosTelegramArchive
```

`configured`, `enabled`, and `started` should all be true. `lastError` should
remain empty. The Telegram bot must be an administrator with permission to
delete messages so Brain can keep the `Memos` topic read-only. Fax intake and
Memos-topic protection deliberately share one Telegram `getUpdates` consumer.

## Telegram Documents Intake

Create a private supergroup topic named `Documents`, record its numeric topic
ID, and configure:

```env
TELEGRAM_TOPIC_DOCUMENTS_ID=...
TELEGRAM_DOCUMENT_INTAKE_ENABLED=true
TELEGRAM_DOCUMENT_MAX_MB=20
TELEGRAM_DOCUMENT_PUBLIC_ORIGIN=https://kaosgdd.net
```

Brain accepts PDFs from that topic, stores an expiring temporary copy, and
replies with `Open`, `Paperless`, and `Delete` actions. Telegram message identity
is stored as an idempotency key, so retries do not create another queue record.
The original topic upload is retained. Paperless becomes authoritative only
after the explicit action.

The hosted Bot API limits this intake to 20 MB. Follow
[Private Telegram Bot API](telegram-bot-api.md) before raising the limit.

HWP handoffs are temporary browser-opening payloads, not document records. Brain
accepts only HWP, HWPX, and HML files, limits them to 50 MB, and removes them
after 30 minutes. They are never submitted to Paperless automatically.

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

Build tagged Brain images on production `kaos` during a quiet maintenance
window. Production Compose references the immutable image tag. Stop a build if
its resource use could affect PACS or another live service. The Control Center
is reserved for Wake-on-LAN transmission.
