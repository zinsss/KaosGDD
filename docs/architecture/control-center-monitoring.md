# Control Center Wake-on-LAN Boundary

Status: planned, not deployed.

## Purpose

The Control Center has one production-facing responsibility: send allowlisted
Wake-on-LAN (WOL) packets when explicitly requested.

It does not own production data, Telegram archives, service monitoring, status
dashboards, alerts, builds, deployments, or service restarts. It is not a
production server or failover server.

## Ownership

| Service | Host | Responsibility |
| --- | --- | --- |
| KaosGDD Brain | production `kaos` | application automation, notifications, logs, and Telegram archives |
| `KaosTelegram` | production `kaos` | service and host health, persistent status messages, alerts, and restricted local recovery |
| `KaosController` | Control Center | confirmed, allowlisted WOL transmission only |

All state and operational history remain on `kaos`. `KaosController` does not
store a health database or supervise production.

## WOL Flow

```text
authorized request
        |
        v
KaosController on Control Center
        |
        v
allowlisted LAN broadcast magic packet
        |
        v
target machine powers on
```

WOL requires the Control Center to be on the target's local layer-2 network.
Tailscale does not relay normal LAN broadcast packets.

## Safety Rules

- Accept only predefined target names and MAC addresses.
- Never accept an arbitrary MAC address or broadcast destination from a user.
- Require an explicit confirmation before sending WOL.
- Restrict callers to configured Telegram group and operator IDs if Telegram
  is used as the command path.
- Keep `KaosController` without SSH credentials, Docker socket access,
  production filesystem mounts, or service-restart authority.
- Record only minimal WOL audit metadata: target, requester, and timestamp.
- Rate-limit repeated requests for the same target.

`KaosTelegram` on `kaos` decides how health and recovery are presented. The
Control Center only transmits the requested magic packet; it does not decide
whether a machine is unhealthy.

## Deployment Order

1. Define the target allowlist and LAN broadcast addresses.
2. Implement the minimal WOL sender on the Control Center.
3. Restrict and test the command path.
4. Verify each target manually without adding monitoring or restart features.
