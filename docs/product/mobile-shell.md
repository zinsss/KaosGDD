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

The UI should continue to depend on adapter-shaped methods, not backend-specific storage:

- `getStatus`
- `getQuickLinks`
- `getEvents`
- `getTasks`
- `getServices`

## Production Safety

The deployed mobile shell is static.

It does not:

- write to Radicale
- call KaosSupplies
- touch PACS
- touch Fax
- access any database
