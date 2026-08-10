# Architecture

KaosGDD v2 is a thin orchestration shell.

It should compose independent services through adapters, not absorb their storage and business logic.

## Principles

- Preserve production PACS first.
- Keep DICOM untouched unless an explicit PACS migration is approved.
- Prefer incremental migration over folder cleanliness.
- Keep independent services authoritative for their own data.
- Keep KaosGDD UI unaware of backend implementation details.
- Do not talk directly to service databases.

## Host Roles

`kaos` is both the development host and the permanent production Docker host.
The responsibilities are colocated, but their files remain separated:

```text
/srv/projects/KaosGDD   source checkout and development work
/srv/kaos/stacks        production Compose definitions
/srv/kaos/data          production persistent data
/srv/kaos/config        production configuration
/srv/kaos/secrets       production secrets
```

Production Docker images are built locally on `kaos` during controlled
maintenance windows and referenced from production Compose by immutable tag.
Development commands must not bind production ports or mount production data.

The Control Center has no development, build, deployment, monitoring, or data
role. It only sends confirmed, allowlisted Wake-on-LAN packets.

## Runtime Boundary

KaosGDD may call:

- HTTP APIs
- CalDAV/CardDAV APIs
- WebDAV-style APIs where appropriate
- service-specific APIs
- Kaos-owned adapter APIs

KaosGDD Brain is the Kaos-owned adapter and orchestration API. It should stay small and should only own logic that cannot cleanly live in the static shell or an independent service.

KaosGDD must not call:

- Paperless PostgreSQL directly
- Wiki.js PostgreSQL directly
- Radicale files directly
- SFTPGo database/files directly
- Vaultwarden database directly
- KaosSupplies database directly; legacy-only while supplies moves to Radicale
- KaosPACS database directly

## Production Edge

Production Caddy runs on the Tailscale IP, not on host port `80`:

```text
100.94.208.16:8080
```

Cloudflare Tunnel targets:

```text
http://caddy:8080
```

KaosPACS keeps host `:80`.

## Legacy Hold

The old KaosGDD frontend is allowed to stay stopped.

The old KaosGDD fax bridge has been replaced by HylaFAX and Brain:

```text
HylaFAX -> Brain -> Telegram
```

Fax receive/send visibility is now owned by the maintained Brain workers.

## Brain

See [KaosGDD Brain](kaosgdd-brain.md).
