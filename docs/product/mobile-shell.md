# Mobile Shell

The mobile shell is the first app-shaped KaosGDD v2 surface.

It keeps the Nord visual language from the mobile v1 prototype and adds route separation:

- Today
- Calendar
- Tasks
- Services

## Adapter Shape

The current data source is a mock adapter in `apps/mobile-shell/app.js`.

This is intentional. The UI should stabilize before Radicale or Kaos service adapters are attached.

The mock adapter now uses Radicale-shaped `VEVENT` and `VTODO` records, then normalizes them for the UI. This keeps the shell close to the future backend without touching live Radicale.

The calendar and task screens now act as the first Radicale frontend prototype:

- switch between `family` and `zin` collections
- show events and tasks from the selected collection
- read live Radicale data through `/api/calendar/bootstrap` when the adapter is configured
- create local draft events shaped like `VEVENT`
- create local draft tasks shaped like `VTODO`
- render legacy description subtasks as interactive checkboxes
- choose event times in 5-minute increments, matching iOS Reminders
- split tasks into `Inbox`, `Dated`, `Done`, and `All`
- show dated VTODO tasks on Calendar by their `DUE` date
- support saved task orders: `Due` and `Created`
- use a Calendar Add flow with Event and Task tabs
- keep Task creation available from Tasks, defaulting to the selected date when opened through Calendar Add
- shape Event creation like iOS Calendar: title, all-day, start/end date and time, weekly/monthly/yearly repeat, alarm time, and memo
- keep the collapsed/expandable month picker on add pages only
- order Add Task fields like iOS Reminders: task name, memo, date picker, time picker, priority
- default Add Task to no due date, with an inline clear button when a due date is selected
- support optional task due time; selected date with blank time defaults to `10:00`, and time without date uses today
- confirm before creating a local task draft whose computed due date/time has already passed
- read VTODO `PRIORITY`, with Add Task using None, Low, Medium, and High and task rows showing iOS-style `!`, `!!`, and `!!!` markers
- use one `Memo` field for VTODO `DESCRIPTION`, including `--` and `-x` subtask lines

The UI should continue to depend on adapter-shaped methods, not backend-specific storage:

- `getCollections`
- `getStatus`
- `getQuickLinks`
- `getEvents`
- `getTasks`
- `createEvent`
- `createTask`
- `getServices`

Task adapter work should follow the [Radicale Task Plan](radicale-task-plan.md).

Memos is included as a service link first. Any future integration should go through a `MemoService` adapter, not direct database reads.

Legacy subtask lines in VTODO descriptions are parsed and rendered in the task list:

```text
-- open subtask
-x completed subtask
```

## Production Safety

The deployed mobile shell is static.

The shell is intended to become the main KaosGDD surface and is served at the portal root. The old static launcher should remain available as a fallback link page while the shell gains features.

It does not:

- write to Radicale
- call KaosSupplies
- touch PACS
- touch Fax
- access any database

If the calendar adapter is unavailable, not configured, or has no live collections, the shell keeps using local preview data so the app remains usable during incremental setup.
