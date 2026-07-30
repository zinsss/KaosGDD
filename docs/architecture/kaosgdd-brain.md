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
| generated market/claim overlays | Brain-calculated, optionally written to Kaos-owned calendar collection |
| documents | Paperless |
| notes/knowledge | Wiki.js |
| files | SFTPGo |
| passwords | Vaultwarden |
| supplies | KaosSupplies |
| fax | KaosFaxMail or legacy bridge until replaced |
| PACS | KaosPACS |

## Radicale Collections

Planned collections:

```text
Kaos_Calendar
Kaos_Tasks
Kaos_Weather
Kaos_Caregiver
```

`Kaos_Weather` and `Kaos_Caregiver` are Kaos-owned generated/structured collections. They should not be edited by normal calendar clients.

## Weather Journals

Use one `VJOURNAL` per location per date.

Fixed history locations:

- `pohang` / `포항`
- `daegu` / `대구`
- `yeongdeok` / `영덕`

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
- calculated total hours

Monthly settings should support:

- hourly wage
- transport fee

Monthly review is calculated by Brain from the journals. The UI should not own the calculation rules.

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

Port the legacy rules:

- Market Saturday is when the day of month is `5`, `10`, `15`, `20`, `25`, or `30` and the weekday is Saturday.
- Claim Day defaults to Friday.
- If the next day is Market Saturday, Claim Day moves to that Saturday.
- If Claim Day falls on a public holiday, shift backward until it is not a public holiday.

Generated events should be readonly from the user UI.

## Migration

Brain `0.2.0-shadow` runs beside the existing `apps/calendar-adapter` and
proxies its calendar bootstrap, weather month, and event/task write routes.
Caddy continues to route browser traffic to the existing adapter. Both profiles
must remain stable in shadow mode before changing that route.
