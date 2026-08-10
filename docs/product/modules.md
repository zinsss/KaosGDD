# Module Plan

## First Surface

Build the first KaosGDD v2 surface as a service cockpit:

- service launcher
- health checks
- module registry
- quick actions
- no database dependency

## Modules

| Module | First behavior | Long-term owner |
| --- | --- | --- |
| Dashboard | Service status and links | KaosGDD |
| Tasks | New task UI working with calendar | KaosGDD UI + Radicale |
| Calendar | Calendar view and adapter | Radicale |
| ROUN timetable | Standalone timetable | KaosGDD |
| Caregiver wage | Standalone family module | KaosGDD |
| Weather | Reuse/adapt current behavior | KaosGDD or weather adapter |
| Notes | Link first, adapter/search later | Wiki.js |
| Memos | Link first, editor after Caregiver and ROUN | Memos |
| Documents | Link first, adapter/search later | Paperless-ngx |
| Files | Link first, adapter later | SFTPGo |
| PDF | Link first, workflow adapter later | Stirling-PDF |
| HWP/HWPX | Browser editor; PDF handoff through Document Inbox | RHWP + KaosGDD Brain |
| Supplies | Buy-list UI with recent presets | KaosGDD Brain + Radicale |
| Fax | Telegram workflow, no KaosGDD page | Brain + HylaFAX |
| PACS | API links only | KaosPACS |

## Not In First Pass

- moving PACS
- moving DICOM
- replacing fax bridge
- rebuilding reminders
- direct database integration
- global search indexing across all services

## ROUN

ROUN timetable stays standalone during the first v2 pass as a template library.

Do not connect it to Radicale/calendar or monthly calendar assignment until the workflow need is clear.

First ROUN behavior:

- edit one weekly template at a time
- save current template
- save as a copy
- rename template
- delete template
- add/edit/remove schedule rows
- show saved templates as a document-like list
- drag/drop saved templates to reorder the list

The first v2 data shape should stay close to the legacy model for easier migration:

```json
{
  "id": "template-id",
  "name": "Basic",
  "items": [
    {
      "id": "item-id",
      "title": "Activity",
      "dayOfWeek": "1",
      "startTime": "09:00",
      "endTime": "09:40",
      "memo": "",
      "color": "pink"
    }
  ]
}
```

Legacy named plans, assignment start dates, and calendar overrides should remain reference material only for now.

Event presets are stored in Brain PostgreSQL so they follow the user across
devices. Personal presets are isolated by portal profile; Family presets are
available from both the main and Family portals. Actual events remain in
Radicale as standard VEVENT records.

## Priority Order

Next module work should focus on:

1. Caregiver wage/calendar support
2. ROUN timetable
3. Memos editor

## Supplies

Supplies should be a separate UI from general tasks, but use Radicale as the
authoritative sync store. Brain provides the KaosSupplies-compatible behavior:
clean title, active-title dedupe, active/done lists, recent preset names, and
`$$ title` capture.

This removes the need for a public `supplies.kaosgdd.net` frontend and also
lets KaosEghis use the KaosGDD tab instead of a separate supplies frontend.

Do not start the Memos editor before the Caregiver and ROUN shapes are usable.

## Memos Editor Plan

Memos remains the authoritative backend for memos. KaosGDD should not create its own notes database.

Planned flow:

```text
KaosGDD UI -> Brain -> Memos API
```

Brain should own the Memos API credential/token. The browser should not store the Memos password.

Main KaosGDD memo UI:

- CodeMirror-style Markdown editor
- Nord dark theme
- raw Markdown first
- optional preview later

Family memo UI:

- simple WYSIWYG editor
- light family theme
- no raw Markdown mode by default
- toolbar limited to:
  - heading
  - bold
  - italic
  - checklist
  - bullet list
  - numbered list
  - link from pasted URL

Both UIs save normal Markdown to Memos.

Supported first Markdown subset:

```md
# Heading

plain paragraph

**bold**
_italic_

- bullet
1. numbered
- [ ] checklist
- [x] completed checklist

[label](https://example.com)
```

Full Memos Markdown support may remain available inside Memos itself. KaosGDD should only expose the subset that is useful in daily family workflows.

## Task Grammar

Radicale-backed tasks should use the legacy KaosGDD subtask grammar inside VTODO descriptions.

See [Radicale Task Plan](radicale-task-plan.md).

## Brain Modules

KaosGDD Brain is the backend home for module logic that should not live in the static shell:

- Radicale task/calendar normalization
- Apple Reminders order compatibility
- Market Saturday and Claim Day overlays
- weather history journals for 포항, 대구, 영천, and 영해
- a saved default weather location plus on-demand selected-day comparison for all four locations
- on-request, today-or-future current-location weather and locality name with no history write
- caregiver journals and monthly wage review

The family calendar exposes the monthly caregiver review through a family-only
`돌봄` entry point. Daily sessions and extra fees are entered from the selected
day in the family calendar. The main KaosGDD profile does not expose this
module.

See [KaosGDD Brain](../architecture/kaosgdd-brain.md).
