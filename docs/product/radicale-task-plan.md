# Radicale Task Plan

KaosGDD tasks should use Radicale as the task/calendar data owner.

The first implementation should keep the task model simple and compatible with iOS, Thunderbird, and plain CalDAV clients.

## Storage Model

Use one CalDAV `VTODO` per task.

Use one CalDAV collection per practical sharing boundary. The first planned KaosGDD collections are:

| Collection | Use |
| --- | --- |
| `zin` | personal work, clinic, document, and migration tasks |
| `family` | shared family tasks and events |

| KaosGDD field | VTODO field |
| --- | --- |
| title | `SUMMARY` |
| memo and subtasks | `DESCRIPTION` |
| due date and optional time | `DUE` |
| completed state | `STATUS` and/or `COMPLETED` |
| priority | `PRIORITY` |
| tags | `CATEGORIES` |
| last activity | `LAST-MODIFIED` |

KaosGDD should not create a separate database for first-pass task data.

Open VTODO items without a `DUE` date should be treated as inbox tasks in KaosGDD. This matches common iOS Reminders behavior, where quick reminders may be created without a date.

Task ordering:

- `Created` order sorts active tasks by `CREATED` ascending.
- `Due` order sorts dated active tasks first by `DUE`, then due time, then `CREATED`.
- In `Due` order, undated active tasks appear below dated tasks and sort by `CREATED` ascending.
- Completed tasks stay separate in `Done` and sort after active tasks in `All`.
- `X-APPLE-SORT-ORDER` is useful for future manual ordering, but first-pass KaosGDD should not depend on it.

KaosGDD task views:

- `Inbox` shows open VTODO items without `DUE`
- `Dated` shows open VTODO items with `DUE`, grouped by due date
- `Done` shows completed VTODO items
- Calendar shows dated VTODO items on their `DUE` date

KaosGDD collection filters:

- `All` shows every visible Radicale collection
- `Family` shows shared family collections when they exist
- `GDD_ZiN` shows `zin`-owned Radicale collections

Calendar/task UI should stay compatible with iOS and Thunderbird. Do not require custom `X-KAOS-*` properties, hidden KaosGDD IDs, or a separate task metadata store for first-pass behavior.

## Legacy Subtask Grammar

Task memo text and subtasks live together inside the VTODO `DESCRIPTION`.

The Add Task UI should expose this as one `Memo` field, not separate custom fields. Subtasks use the legacy KaosGDD grammar inside that memo:

Due time rules:

- Add Task defaults to no due date.
- If a date is selected and no time is entered, use the configured default time, currently `10:00`.
- If only a time is entered, use today as the due date.
- If the computed due date/time is already past, ask for confirmation before creating the task.

Priority rules:

- Use the standard VTODO `PRIORITY` field only.
- Treat `1-3` as High, `4-6` as Medium, and `7-9` as Low.
- Treat missing priority or `0` as no priority.
- Add Task should write `1` for High, `5` for Medium, `9` for Low, or no value for None.
- Task rows should display priority with iOS-style markers: `!`, `!!`, and `!!!`.

```text
-- open subtask
-x completed subtask
```

Rules:

- Lines beginning with `-- ` are open subtasks.
- Lines beginning with `-x ` are completed subtasks.
- Other description lines are normal notes.
- KaosGDD may render these lines as interactive checkboxes.
- When a subtask is toggled, KaosGDD rewrites only the marker for that line.

Example:

```text
Fax follow-up notes

-- call clinic
-- attach PDF
-x send fax
```

## Compatibility

This approach keeps tasks readable in clients that do not understand KaosGDD subtasks.

iOS Calendar, Thunderbird, and other CalDAV clients should still see normal task notes. They may not render subtasks as checkboxes, but the text remains understandable.

## Not In First Pass

- nested subtasks
- separate KaosGDD task database
- `RELATED-TO` task hierarchy
- custom CalDAV extensions
- advanced recurrence handling
- live CalDAV writes from the static shell

## Later Options

If hierarchy becomes important, KaosGDD may add visual grouping with `RELATED-TO` or categories. That should only happen after the flat legacy-description grammar proves insufficient.

The next implementation step is a small authenticated adapter service that can read and write `VEVENT` and `VTODO` records through Radicale. The browser UI should call that adapter, not Radicale storage paths or files directly.
