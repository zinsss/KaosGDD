# ADR 0003: Leave Host Port 80 To KaosPACS

## Status

Accepted.

## Context

KaosPACS is production medical infrastructure and currently owns host port `80` on the production server.

The new edge layer can operate through Cloudflare Tunnel without requiring local host port `80`.

## Decision

Keep host port `80` assigned to KaosPACS.

Run production Caddy on:

```text
100.94.208.16:8080
```

Cloudflare Tunnel routes to:

```text
http://caddy:8080
```

## Consequences

- PACS remains stable.
- New HTTPS services work through Cloudflare Tunnel.
- Caddy can later take `80` only if PACS routing is explicitly planned.
