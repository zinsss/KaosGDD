# Radicale Task Plan

KaosGDD tasks should use Radicale as the task/calendar data owner.

The first implementation should keep the task model simple and compatible with iOS, Thunderbird, and plain CalDAV clients.

## Storage Model

Use one CalDAV `VTODO` per task.

| KaosGDD field | VTODO field |
| --- | --- |
| title | `SUMMARY` |
| notes and subtasks | `DESCRIPTION` |
| due date | `DUE` |
| completed state | `STATUS` and/or `COMPLETED` |
| tags | `CATEGORIES` |

KaosGDD should not create a separate database for first-pass task data.

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

## Later Options

If hierarchy becomes important, KaosGDD may add visual grouping with `RELATED-TO` or categories. That should only happen after the flat legacy-description grammar proves insufficient.
