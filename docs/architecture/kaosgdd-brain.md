# KaosGDD Brain

KaosGDD Brain is the v2 backend boundary for orchestration logic.

The static/mobile shell should stay UI-focused. Brain provides the API surface that joins Radicale, generated context, service status, and future workflow adapters.

## Why Brain Exists

Radicale can own user calendar and task data, but it does not provide every KaosGDD behavior:

- task ordering compatible with Apple Reminders
- generated clinic calendar overlays
- daily weather history
- live weather lookup for selected or current location
- caregiver monthly wage calculations
- cross-service status and workflow routing

Brain owns those joins and calculations. It should not become a generic application platform.

## Ownership Rules

| Data | Owner |
| --- | --- |
| user calendar events | Radicale |
| user tasks/reminders | Radicale |
| weather daily history | Kaos-owned Radicale `VJOURNAL` collection |
| caregiver day records | Kaos-owned Radicale `VJOURNAL` collection |
| caregiver monthly wage settings | Kaos-owned Radicale `VJOURNAL` collection |
| Korean holidays and observances | Existing Family Radicale calendar, synchronized by Brain |
| generated market/claim overlays | Brain-calculated, optionally written to Kaos-owned calendar collection |
| documents | Paperless |
| notes/knowledge | Wiki.js |
| files | SFTPGo |
| passwords | Vaultwarden |
| supplies buy-list VTODOs | Radicale |
| supplies presets/recent history | Brain PostgreSQL |
| fax | HylaFAX transport with Brain Telegram intake, notification, and archive |
| PACS | KaosPACS |

## Radicale Collections

Planned collections:

```text
Kaos_Calendar
Kaos_Tasks
Kaos_Weather
Kaos_Caregiver
Kaos_Supplies
```

`Kaos_Weather` and `Kaos_Caregiver` are Kaos-owned generated/structured collections. They should not be edited by normal calendar clients.

`Kaos_Supplies` is a dedicated task collection owned by the `supplies` Radicale
account. It may sync through CalDAV clients, but KaosGDD presents it as a
separate buy-list UI instead of mixing it into general tasks.

## Supplies

The old KaosSupplies API behavior is the compatibility reference, but the new
runtime path is:

```text
KaosGDD UI -> Brain -> Radicale Kaos_Supplies VTODO collection
```

Brain should preserve the useful KaosSupplies rules:

- active list: oldest created first
- done list: newest completed first
- clean title: trim and collapse whitespace
- normalized title: lowercase, trim, collapse whitespace
- active-title dedupe by normalized title
- done items may be re-added as new active items
- presets are recent names, capped to 15, stored in Brain PostgreSQL
- `$$ title` capture creates a supply item

Do not expose a new public supplies subdomain unless a future workflow needs it.

## Weather Journals

Use one `VJOURNAL` per location per date.

Fixed history locations:

- `pohang` / `포항`
- `daegu` / `대구`
- `yeongcheon` / `영천`
- `yeonghae` / `영해`

The legacy `yeongdeok` / `영덕` key remains readable for existing weather
journals, but new portal defaults do not advertise it.

Only daily history is stored:

- min temperature
- max temperature
- condition/weather code
- glyph/label

Morning/afternoon/evening/night dayparts are live forecast context only and should not be stored as history.

Current location is on request only:

- no automatic geolocation prompt
- no current-location history write by default
- live weather may use browser coordinates when the user selects Current

## Caregiver Journals

Use `VJOURNAL` for caregiver day records and monthly settings.

Daily records should support:

- sessions, such as `09:00-12:30`
- optional extras, such as transport or one-off fees
- optional notes

Monthly settings should support:

- hourly wage
- transport fee

Daily records use deterministic UIDs in the form
`KAOS-CAREGIVER-DAY-YYYYMMDD`. Monthly settings use
`KAOS-CAREGIVER-SETTINGS-YYYYMM`. Their `DESCRIPTION` values contain typed JSON
payloads, while the summary remains human-readable.

Monthly review is calculated by Brain from session minutes. It includes worked
days, total hours, base pay, daily extras, monthly transport, total payout, and
the per-day breakdown. When a month has no explicit settings, Brain uses the
latest settings from an earlier month. The UI should not own these rules.

The family calendar selected-day view writes daily sessions and extras through
Brain. New records start with a `09:00-10:00` draft, use five-minute time
increments, and may contain multiple sessions and multiple labeled extras.

## Task Ordering

Brain should read Apple Reminders order when present:

```text
X-APPLE-SORT-ORDER
```

Task ordering rule:

1. separate active and completed tasks by view
2. sort by `X-APPLE-SORT-ORDER` when present
3. if missing, fall back to `CREATED` ascending for undated tasks
4. for dated tasks, keep due date first, then Apple order/priority/time as needed
5. when Brain writes ordering later, use unique spaced values to avoid duplicates

Brain should not depend on duplicate Apple order behavior. iOS may preserve client cache order for ties.

## Generated System Calendar

Brain imports the current and next year from Google's public Korean calendar
into the existing Family calendar. Imported VEVENTs use `KAOS-SYSTEM` and
`KAOS-GOOGLE-HOLIDAY` categories plus exactly one classification category:

- `KAOS-PUBLIC-HOLIDAY`: red day number, like Sunday
- `KAOS-OBSERVANCE`: dim informational calendar entry

Settings exposes the classification as a checkbox. A later source sync keeps
the user's existing classification. These generated entries are not editable
through the normal event form.

Port the legacy rules:

- Market Saturday is when the day of month is `5`, `10`, `15`, `20`, `25`, or `30` and the weekday is Saturday.
- Claim Day defaults to Friday.
- If the next day is Market Saturday, Claim Day moves to that Saturday.
- If Claim Day falls on a public holiday, shift backward until it is not a public holiday.

Generated events should be readonly from the user UI.

## Migration

Brain `0.3.1-shadow` runs beside the existing `apps/calendar-adapter` and
proxies its calendar bootstrap, weather month, and event/task write routes.
Caddy continues to route calendar and weather browser traffic to the adapter.
Only `family.kaosgdd.net/api/caregiver/*` is routed to Brain; the main profile
has no caregiver route.
