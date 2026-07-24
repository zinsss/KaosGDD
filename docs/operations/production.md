# Production Operations

## Current Production Host

Permanent production host:

```text
/srv/kaos
```

Important stack groups:

```text
/srv/kaos/stacks/edge
/srv/kaos/stacks/platform
/srv/kaos/stacks/documents
/srv/kaos/stacks/clinic
/srv/kaos/stacks/pacs
```

## Edge

Caddy and cloudflared run on production without using host port `80`.

```text
Caddy:       100.94.208.16:8080
cloudflared: outbound connector
PACS:        host :80
```

## Temporary KaosGDD Launcher

Current placeholder:

```text
/srv/kaos/stacks/platform/kaosgdd/portal
```

Public URL:

```text
https://family.kaosgdd.net
```

Replace this with the real v2 shell when ready.

## Guardrails

- Do not wipe production.
- Do not move DICOM casually.
- Do not migrate KaosPACS until last.
- Do not stop the legacy KaosGDD backend until fax/Pushover is replaced.
- Keep service data owned by service-specific stacks.

## Backup

Production backup source list:

```text
/srv/kaos/scripts/backup-manifest.sh
```

Synology is backup storage only.
