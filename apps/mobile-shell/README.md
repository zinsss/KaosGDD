# KaosGDD Mobile Shell

Mobile-first KaosGDD app shell.

This is the first app-shaped version after the mobile v1 prototype. The frontend remains static and keeps mock fallback data, while production calendar/task operations go through the server-side calendar adapter.

## Routes

- `#/today`
- `#/calendar`
- `#/tasks`
- `#/services`

## Boundaries

Data enters the UI through adapter-shaped functions in `app.js`. Calendar and task reads/writes use `/api/calendar/*`; mock data remains a local fallback when the adapter is unavailable.

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

Deploy without copying the private checkout permissions onto the nginx web root:

```bash
rsync -rltp --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r apps/mobile-shell/ /srv/kaos/data/kaosgdd/portal/
rsync -rltp --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r apps/mobile-shell/ /srv/kaos/data/kaosgdd/portal/app/
```

## Localization

Main KaosGDD uses the English fallback copy in `app.js`. All Family Korean UI copy is collected in `translations.js`.

Edit translation values only; keep dictionary keys and `{placeholder}` names unchanged. Bump the `translations.js` query version in `index.html` when deploying revised copy.
