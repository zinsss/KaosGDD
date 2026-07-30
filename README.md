# KaosGDD

KaosGDD is the Kaos platform orchestration shell.

This repository is the new v2 line. It intentionally does not continue the old KaosGDD backend as a generic application platform.

## Purpose

KaosGDD v2 owns:

- dashboard
- navigation
- workflow UI
- cross-service orchestration
- service health/status surface
- adapter boundaries
- clinic and family-specific modules that do not belong in generic services

KaosGDD v2 does not own generic service data when a dedicated system is authoritative.

## Current Production Shape

The production server is the ODROID host under `/srv/kaos`.

Public HTTPS is routed through Cloudflare Tunnel and Caddy:

```text
Cloudflare
-> cloudflared
-> Caddy on 100.94.208.16:8080
-> service containers
```

KaosPACS keeps host port `80`. KaosGDD and the new service layer do not require port `80`.

## First Milestone

The first milestone is a thin service cockpit:

- links to live services
- health/status checks
- module registry
- no direct database access
- no fax migration
- no PACS migration

## Mobile Prototype

The first mobile-first design prototype is in:

```text
prototypes/mobile-v1
```

It is static and safe to open locally. It uses old KaosGDD as a design reference, not as an implementation base.

## Mobile Shell

The first app-shaped mobile shell is in:

```text
apps/mobile-shell
```

It has separate Today, Calendar, Tasks, and Services routes. The frontend is static, but its calendar and task writes go through the authenticated server-side calendar adapter.

The current temporary launcher is served from:

```text
/srv/kaos/stacks/platform/kaosgdd/portal
```

## Brain

The v2 backend boundary is `KaosGDD Brain`:

```text
apps/brain
```

Brain is the small orchestration backend for adapter APIs, Radicale normalization, generated calendar overlays, weather history, caregiver calculations, and service status. Version `0.2.0-shadow` runs internally on port `8092` beside the live adapter with read and write contract parity; Caddy still routes browser traffic to the existing adapter on `8091`.

## Source Of Truth

Start with the docs in this repository:

- [Architecture](docs/architecture/architecture.md)
- [KaosGDD Brain](docs/architecture/kaosgdd-brain.md)
- [Service Map](docs/architecture/service-map.md)
- [Module Plan](docs/product/modules.md)
- [Operations](docs/operations/production.md)
- [ADR 0001](docs/decisions/0001-thin-orchestration-shell.md)
