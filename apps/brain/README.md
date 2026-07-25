# KaosGDD Brain

KaosGDD Brain is the small backend for KaosGDD v2 orchestration.

It is not a replacement for Radicale, Paperless, Wiki.js, KaosSupplies, KaosFaxMail, or PACS. It exists for logic that the static shell cannot do safely by itself.

## Scope

Brain owns:

- adapter APIs used by the KaosGDD shell
- Radicale CalDAV/CardDAV access
- task and calendar normalization
- Apple Reminders ordering compatibility
- generated calendar overlays, such as Market Saturday and Claim Day
- weather fetch and generated weather history journals
- caregiver journal normalization and monthly review calculations
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
/srv/kaos/secrets/kaosgdd-adapters.env
```

Brain should remain independently restartable from the static portal.
