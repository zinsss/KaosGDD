# KaosGDD Mobile Shell

Mobile-first KaosGDD app shell.

This is the first app-shaped version after the mobile v1 prototype. It remains static and mock-backed so the interface can settle before service adapters are attached.

## Routes

- `#/today`
- `#/calendar`
- `#/tasks`
- `#/services`

## Boundaries

Data enters the UI through adapter-shaped functions in `app.js`. The current adapter is mock-only and performs no production writes.

Future adapters:

- Calendar and task data -> Radicale adapter
- Supplies -> KaosSupplies adapter
- Documents -> Paperless adapter
- Knowledge -> Wiki.js adapter

## Deploy

The production test deployment is served from the existing KaosGDD portal nginx container under:

```text
/          main app
/app/
```

The old service launcher remains available as `/launcher.html`. The static prototype remains available as `/mobile-v1/`.
