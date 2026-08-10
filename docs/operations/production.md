# Production Operations

## Current Production Host

The permanent production host and development host are the same `kaos` ODROID.
Keep their filesystem responsibilities separate:

```text
/srv/projects/KaosGDD   source checkout and development work
/srv/kaos               production stacks, data, config, secrets, and operations
```

Build production Docker images locally on `kaos` during a quiet maintenance
window. Tag images immutably and make production Compose reference that tag;
do not run production from a mutable development container. A build must be
stopped if it affects PACS or another live service.

The Control Center only sends allowlisted Wake-on-LAN packets. It does not
develop, build, deploy, monitor, or store Kaos services.

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
- Keep HylaFAX and Brain independently restartable; neither depends on the
  retired legacy notification bridge.
- Keep service data owned by service-specific stacks.

## Backup

Production backup source list:

```text
/srv/kaos/scripts/backup-manifest.sh
```

Synology is backup storage only.
