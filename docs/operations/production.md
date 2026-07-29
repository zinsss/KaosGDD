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

KaosGDD adapter routes are host-scoped in Caddy:

```text
kaosgdd.net/api/calendar/*
family.kaosgdd.net/api/calendar/*
kaosgdd.net/api/weather/*
family.kaosgdd.net/api/weather/*
```

Do not use path-only adapter matchers because they expose the adapter under unrelated Kaos service hostnames.

## KaosGDD Portal

Current shell:

```text
/srv/kaos/stacks/platform/kaosgdd/portal
```

Public URLs:

```text
https://kaosgdd.net
https://family.kaosgdd.net
```

## KaosGDD Brain

Brain is planned under:

```text
/srv/kaos/stacks/platform/kaosgdd/brain
/srv/kaos/data/kaosgdd/brain
```

The current live first Brain slice remains the calendar adapter until the new Brain endpoint reaches parity.

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
