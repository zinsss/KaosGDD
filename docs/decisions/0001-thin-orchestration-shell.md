# ADR 0001: KaosGDD v2 Is A Thin Orchestration Shell

## Status

Accepted.

## Context

The old KaosGDD accumulated generic backend responsibilities: tasks, notes, files, family areas, reminders, fax views, supplies workflows, and other state.

The v2 platform now has dedicated services for many generic responsibilities:

- Paperless for documents
- Wiki.js for knowledge and notes
- Radicale for calendar-like data
- SFTPGo for files
- Stirling-PDF for PDF workflows
- Vaultwarden for passwords
- KaosSupplies for supplies

KaosPACS remains production medical infrastructure and is not part of this migration phase.

## Decision

KaosGDD v2 will be a thin orchestration shell.

It owns UX, workflow, navigation, service status, and adapters.

It does not own generic service data when a dedicated service is authoritative.

## Consequences

Good:

- Less custom backend surface.
- Easier incremental migration.
- Service data remains portable.
- PACS risk stays isolated.

Tradeoffs:

- KaosGDD must handle adapter failures well.
- Some workflows require cross-service orchestration.
- Global search will need explicit indexing rules later.

## First Implementation Direction

Start with a service cockpit, then build Tasks + Calendar as the first real workflow.
