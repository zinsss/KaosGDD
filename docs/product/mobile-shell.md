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

The UI should continue to depend on adapter-shaped methods, not backend-specific storage:

- `getStatus`
- `getQuickLinks`
- `getEvents`
- `getTasks`
- `getServices`

Task adapter work should follow the [Radicale Task Plan](radicale-task-plan.md).

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
