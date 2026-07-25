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
| notes and subtasks | `DESCRIPTION` |
| due date | `DUE` |
| completed state | `STATUS` and/or `COMPLETED` |
| tags | `CATEGORIES` |

KaosGDD should not create a separate database for first-pass task data.

Open VTODO items without a `DUE` date should be treated as inbox/now tasks in KaosGDD. This matches common iOS Reminders behavior, where quick reminders may be created without a date.

## Legacy Subtask Grammar

Subtasks live inside the VTODO `DESCRIPTION` using the legacy KaosGDD grammar.

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
