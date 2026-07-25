# Calendar Adapter Operations

The KaosGDD calendar adapter is the read-only bridge from the browser shell to Radicale.

## Production Paths

```text
/srv/kaos/stacks/platform/kaosgdd/calendar-adapter/compose.yaml
/srv/kaos/data/kaosgdd/calendar-adapter/server.py
/srv/kaos/secrets/kaosgdd-adapters.env
```

The portal also proxies `/api/calendar/*`:

```text
/srv/kaos/config/kaosgdd/portal/nginx.conf
/srv/kaos/stacks/platform/kaosgdd/portal/compose.yaml
```

Caddy has a matching local path route as well:

```text
/srv/kaos/config/Caddyfile
```

## Safety

The adapter uses CalDAV HTTP requests only.

It does not:

- write to Radicale
- read Radicale collection files directly
- access databases
- touch PACS, fax, or clinic services

## Validate

```bash
curl http://100.94.208.16:8091/health
curl http://100.94.208.16:8091/api/calendar/bootstrap
curl https://kaosgdd.net/api/calendar/bootstrap
```

With blank credentials, the expected response is:

```json
{"configured": false, "live": false}
```

## Enable Live Reads

Set these values in `/srv/kaos/secrets/kaosgdd-adapters.env`:

```text
RADICALE_USERNAME=
RADICALE_PASSWORD=
```

Then restart only the adapter:

```bash
cd /srv/kaos/stacks/platform/kaosgdd/calendar-adapter
docker compose up -d
```
