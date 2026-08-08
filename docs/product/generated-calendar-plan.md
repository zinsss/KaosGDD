# Generated Calendar Plan

## Status

Planned after the Korean public-holiday sync.

The public-holiday foundation is already live:

- Google Korea calendar entries are synchronized by Brain.
- Entries are stored in the existing Family Radicale calendar.
- Checked public holidays are red like Sundays.
- Unchecked observances remain dim informational entries.
- Manual classification survives later source synchronization.

This document covers the remaining Market Day and Claim Day behavior.

## Ownership

Brain owns the deterministic generation rules.

Radicale remains the source of truth for generated calendar entries. Brain must
write them into the existing `GDD_ZiN` calendar rather than introduce another
calendar or parallel event database.

The portal reads the generated entries through the existing calendar adapter.
Generated entries are read-only in KaosGDD's normal event forms.

## Market Day

Every date whose day of month is one of the following is a Market Day:

```text
5, 10, 15, 20, 25, 30
```

This applies on every weekday, not only Saturday.

Calendar behavior:

- Show a blue dot in the month cell for every Market Day.
- Do not include the generated marker in the normal event-count number.
- Keep the day number's normal Sunday, Saturday, and public-holiday color.
- A Market Day that falls on Saturday is also a Market Saturday for Claim Day
  calculation.

Suggested CalDAV categories:

```text
KAOS-SYSTEM
KAOS-MARKET-DAY
KAOS-MARKET-SATURDAY    # added only when the date is Saturday
```

Use a stable UID derived from the date, for example:

```text
KAOS-MARKET-2026-08-10
```

## Claim Day

Generate one Claim Day per week.

Rules, preserved from KaosGDD legacy:

1. Claim Day normally falls on Friday.
2. If the following Saturday is a Market Saturday and is not a checked public
   holiday, move that week's Claim Day from Friday to Saturday.
3. A checked public holiday takes precedence over the Market Saturday rule. If
   Market Saturday is also a public holiday, do not place Claim Day on Saturday.
4. If the Friday or selected Claim Day is a checked public holiday, move Claim
   Day backward one day at a time until it reaches a date that is not a checked
   public holiday.
5. Informational observances do not move Claim Day.
6. Recalculate immediately after a holiday classification changes.

Examples:

```text
Friday 2026-01-02                         -> Claim Day 2026-01-02
Friday 2026-01-09 + Market Sat 01-10     -> Claim Day 2026-01-10
Market Sat 01-10 is a public holiday      -> Claim Day 2026-01-09
Market Sat and Friday are public holidays -> move backward to Thursday
Friday marked as public holiday           -> move backward to Thursday
```

Suggested CalDAV categories:

```text
KAOS-SYSTEM
KAOS-CLAIM-DAY
```

Use a stable UID based on the Friday that owns the weekly calculation, not only
the final shifted date. This lets Brain move an existing event instead of
creating a duplicate when holiday classification changes.

```text
KAOS-CLAIM-WEEK-2026-01-09
```

## CalDAV Representation

Generated items should be standard all-day `VEVENT` records in `GDD_ZiN`.

Required properties:

```text
UID
SUMMARY
DTSTART;VALUE=DATE
DTEND;VALUE=DATE
CATEGORIES
CREATED
LAST-MODIFIED
```

No private database is needed for generated event content. A small Brain sync
status record is acceptable, but Radicale remains authoritative.

Brain synchronization must be idempotent:

- create missing generated events
- update changed dates or categories
- delete stale generated events inside the managed date range
- never alter ordinary user events
- never alter generated records without the expected `KAOS-SYSTEM` category

Generate at least the current and next year, matching the holiday horizon.

## Portal Behavior

Both main and Family portals can show the resulting context because both read
the shared Family holiday data and the main portal reads `GDD_ZiN`.

Main month grid:

- blue dot: Market Day
- red day number: checked public holiday
- existing event count: ordinary events only
- existing task count: due tasks only

Selected-day agenda:

- generated Market Day and Claim Day entries may appear as compact read-only
  context
- informational holiday entries remain dim
- generated entries must not open the normal edit form

The Family portal should not gain write access to `GDD_ZiN`. If Market/Claim
context is shown there, it must come from a read-only Brain response or the
existing main-profile data boundary, not expanded Family credentials.

## Settings

Add a collapsed **Custom Events** section to the main KaosGDD Settings page.

```text
Custom Events

Market Days    [enabled]
Claim Day      [enabled]
```

Both controls default to enabled.

- Disabling Market Days removes managed Market Day VEVENTs from the generated
  range, which also removes the blue month-grid dots.
- Disabling Claim Day removes managed Claim Day VEVENTs from the generated
  range.
- Claim Day calculation still uses deterministic Market Saturday dates when
  Market Days are hidden or disabled. The display control must not change the
  underlying business rule.
- Re-enabling either control runs an idempotent synchronization immediately.
- These orchestration preferences may live in Brain PostgreSQL; generated event
  content remains authoritative in Radicale.
- The Family portal does not receive these write controls because the generated
  entries belong to `GDD_ZiN`.

Holiday checkboxes remain the only user input affecting Claim Day. Changing a
checkbox should:

1. update the Family holiday VEVENT classification
2. trigger Claim Day recalculation
3. refresh calendar data

A manual "Regenerate system calendar" action may be added for recovery, but
normal operation must use automatic idempotent synchronization.

## Claim Task Decision

Legacy KaosGDD also generated a `청구하기` task on Claim Day with evening due
and reminder times. Do not restore that automatically in the first calendar
slice.

If added later, it must be a normal standard `VTODO`, deduplicated by stable UID,
and compatible with iOS Reminders. Its due time and alarm policy require a
separate explicit decision.

## Implementation Order

1. Add pure date-calculation functions with legacy parity tests.
2. Extend the adapter with internal `GDD_ZiN` generated-event CRUD.
3. Add Brain's idempotent current/next-year synchronization.
4. Trigger recalculation after holiday sync and classification changes.
5. Add the main Settings **Custom Events** controls.
6. Add Market Day blue-dot rendering without changing event counts.
7. Add read-only selected-day context.
8. Deploy beside the existing calendar path and verify one full month.

## Required Tests

Date calculation:

- all `5/10/15/20/25/30` dates are Market Days regardless of weekday
- only Saturday Market Days trigger the Saturday Claim Day override
- a public holiday on Market Saturday suppresses the Saturday override
- ordinary Friday remains Claim Day
- public holiday shifts Claim Day backward
- consecutive public holidays shift repeatedly
- observance does not shift Claim Day
- year and month boundaries are correct

Synchronization:

- repeated sync creates no duplicates
- disabling and re-enabling either Custom Events control is idempotent
- Claim Day still observes Market Saturday when Market Day display is disabled
- holiday reclassification moves the existing Claim Day event
- stale generated entries are removed
- ordinary `GDD_ZiN` events are untouched
- generated entries reject normal edit/delete operations

UI:

- blue dot appears on every Market Day
- public-holiday red day number and Market Day blue dot can coexist
- generated events do not increase ordinary event counts
- mobile and desktop month grids remain stable

## Non-Goals

- No new Radicale account or collection.
- No direct database access from KaosGDD UI.
- No automatic Claim Day task in the first slice.
- No push notifications; native calendar/task clients remain responsible for
  notifications.
