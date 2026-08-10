# Control Center Monitoring Plan

Status: planned, not deployed.

## Purpose

`KaosController` is an independent monitoring and recovery-control service
running on the Control Center ODROID. It is not part of KaosGDD Brain and does
not make the Control Center a failover server.

It provides:

- external reachability checks for production systems
- the persistent Telegram System Status message
- pushed Telegram `System Alerts` messages for failures and recoveries
- manual, protected Wake-on-LAN actions

Brain remains an application orchestration service. It may expose detailed
health data, but it must not supervise itself.

## Service Names and Ownership

The Telegram architecture contains three separate workers:

| Service | Host | Responsibility |
| --- | --- | --- |
| KaosGDD Brain | production `kaos` | application notifications, logs, fax archives, mail archives, and personal Memos archives |
| `KaosTelegram` | production `kaos` | local service health, persistent Services Status message, and allowlisted local service restarts |
| `KaosController` | Control Center | machine reachability, persistent System Status message, and WOL |

Use separate Telegram bot credentials. Each worker owns its bot's long polling,
message IDs, and callbacks. Brain has no monitoring or recovery authority.
`KaosTelegram` has no WOL authority. `KaosController` has no production service
restart authority.

Do not run `getUpdates` for one Telegram bot token from multiple workers. The
separate bot identities prevent callback contention and limit the effect of a
leaked token.

## Runtime Boundary

```text
Control Center ODROID
└── KaosController
    ├── Telegram Bot API long polling
    ├── Telegram Bot API delivery
    ├── machine reachability checks
    └── Wake-on-LAN sender

Production kaos
├── KaosGDD Brain
│   └── notifications, logs, fax/mail/Memos archives
├── KaosTelegram
│   ├── local service health checks
│   ├── Services Status message
│   └── restricted local service-control command
└── service-specific health endpoints
```

Long polling avoids exposing a public webhook on the Control Center. WOL is
available only while the Control Center is on the same layer-2 network as the
target. Tailscale does not carry normal LAN broadcast packets.

## Telegram Supergroup Topics

Use one private Kaos supergroup with these fixed topics. Topic routing uses
numeric `message_thread_id` values stored outside Git; names are documentation
and must not be used as runtime identifiers.

All inbound bot actions are restricted to that exact supergroup ID and require
Telegram's `supergroup` chat type. Private chats and other groups are not valid
Kaos command channels.

| Topic | Owner | Purpose | Notification behavior |
| --- | --- | --- | --- |
| `System Controller` | `KaosController`, `KaosTelegram` | persistent system/services status and confirmed control actions | status edits silent; confirmations transient |
| `System Alerts` | monitoring workers | infrastructure failure and recovery transitions | pushed |
| `System Logs` | all Kaos workers | concise operational and audit logs | silent |
| `Notifications` | Brain | general notifications, including calendar and tasks | pushed |
| `Fax` | Brain | received/sent fax archive; sending may be added later | archive uploads silent |
| `Mail` | Brain | Naver `각종공문` and `세무사` summaries and attachments | summary pushed; attachments silent |
| `Memos` | Brain | personal Memos archive | silent |

`System Controller` contains exactly two persistent messages owned by two
different bots.

### System Status

Owner: `KaosController`.

```text
System Status
Updated: 2026.08.10 22:10

[🟢 Kaos]      [🟢 YHSHFM]
[🟢 KaosINJ]   [🟢 Synology]
```

### Services Status

Owner: `KaosTelegram`.

```text
Services Status

[🟢 KaosGDD]     [🟢 KaosPACS]
[🟢 KaosEghis]   [🟢 Memos]
[🟢 Radicale]    [🟢 Paperless]
[🟢 Vaultwarden] [🟢 Fax]
[🟢 Caddy]       [🟢 Cloudflare]
[🟢 RustDesk]    [🟢 Backups]
```

Status meanings:

| Indicator | Meaning |
| --- | --- |
| 🟢 | healthy |
| 🟡 | degraded, starting, or restarting |
| 🔴 | confirmed unavailable |
| ⚪ | disabled, unknown, or not monitored |

Each owner sends and pins its message on first successful startup and stores the
message ID. Later checks use Telegram `editMessageText`; routine checks never
append new topic messages. If a dashboard message is deleted, its owner
recreates it, pins it, and saves the replacement ID.

The timestamp must remain visible on each message. A stale System Status
timestamp indicates that the Control Center or `KaosController` is unavailable.
A stale Services Status timestamp, combined with a red Kaos system state,
indicates that production or `KaosTelegram` is unavailable.

## Health Evaluation

Do not mark a target red after one timeout.

1. First failed check: retain the previous state and increment a failure count.
2. Second failed check: mark the target yellow.
3. Third consecutive failed check: mark it red and publish one transition
   alert.
4. First successful check after red: mark it green and publish one recovery
   alert.

`KaosController` host checks distinguish an offline machine from an available
machine. A service failure reported by `KaosTelegram` must never expose a host
WOL action.

Planned host checks:

- ICMP or TCP reachability
- Tailscale reachability where applicable
- filesystem capacity and inode capacity
- SMART/NVMe health
- CPU temperature, memory, swap, and sustained load
- Docker daemon availability
- backup freshness after Synology backup preparation is complete

Planned `KaosTelegram` service checks:

- service-specific HTTP health endpoint where available
- Docker health state where available
- required TCP listener only when no application endpoint exists
- HylaFAX scheduler, fax queue, `faxgetty`, modem device, and recent failures
- Caddy and cloudflared path reachability from outside production

PACS checks are observation-only and must not read, modify, move, or validate
individual DICOM studies.

## Wake-on-LAN

WOL is manual and appears only for a system confirmed offline/red.

- Green: no WOL action.
- Yellow: no WOL action.
- Red and host offline: show `Wake {system}`.
- Unknown: recheck before offering WOL.

After confirmation, send the predefined magic packet several times, mark the
system yellow with `Starting`, and poll until it becomes healthy or the startup
deadline expires. Remove the WOL action when the system returns green.

WOL must never be used as reset and must never run automatically after a health
failure. Each target uses a configured MAC address; chat input cannot supply a
MAC address or network destination.

## Service Restart Actions

A service confirmed red may expose `Restart {service}` from `KaosTelegram`. A
restart remains manual even when Docker uses `restart: unless-stopped`.

Restart flow:

1. Require three consecutive failed checks.
2. Show an action only for an allowlisted service.
3. Require transient confirmation.
4. Recheck that the service is still red.
5. Mark the service yellow with `Restarting`.
6. Run the exact mapped restart command.
7. Poll until healthy or until the restart deadline expires.
8. Enforce a per-service cooldown and maximum attempt count.

Initial policy:

| Policy | Services |
| --- | --- |
| restartable | KaosGDD portal/Brain/adapters, Memos frontends, Paperless web, Wiki.js, Stirling-PDF, Vaultwarden, Radicale, Caddy, cloudflared |
| extra confirmation/manual diagnosis | HylaFAX/Fax, RustDesk, supporting non-PACS databases |
| observation only | KaosPACS, Orthanc storage, PACS PostgreSQL, DICOM storage, KaosEghis |

Restart one service rather than an entire stack whenever Compose ownership and
dependencies allow it.

## Transient Confirmation

Telegram does not provide ephemeral bot messages. The action owner creates a
normal confirmation message and deletes it after ten seconds. `KaosController`
owns WOL confirmations; `KaosTelegram` owns service restart confirmations.

```text
Restart Memos?

[Confirm] [Cancel]

Expires in 10 seconds
```

The confirmation payload contains a one-time signed token with:

- requesting Telegram user ID
- action
- target
- issue time and expiry
- random nonce

Only configured operator user IDs may confirm. Confirm and Cancel both delete
the prompt immediately. Expired, reused, mismatched, or stale-state tokens do
nothing. A surviving prompt after a process restart is still rejected after
its signed expiry.

## Remote-Control Security

Brain's Telegram bot has no monitoring or recovery permissions.
`KaosController` has no SSH, Docker socket, or service restart access to
production. `KaosTelegram` uses a restricted local helper and must not possess
unrestricted root, Docker socket, or shell access.

Production exposes one restricted local service-control path for
`KaosTelegram` that:

- accepts only predefined target IDs and actions
- maps each ID to one exact command
- rejects shell metacharacters and arbitrary arguments
- writes operator, action, target, result, and timestamp to the system journal
- returns a minimal structured result

Store Telegram, signing, MAC-address, and message-ID state
outside the Git repository with mode `0600`. Telegram callbacks are authorized
by numeric user ID, not display name or username.

## Notifications and Logs

- Brain Telegram topics: `Notifications`, `System Logs`, `Fax`, `Mail`, and
  personal `Memos` archives.
- Telegram `System Controller`: two persistent status messages plus transient
  control confirmations.
- Telegram `System Alerts`: pushed infrastructure failure and recovery
  transitions.
- `KaosController` Telegram `System Alerts`: machine failure and recovery transitions.
- `KaosTelegram` Telegram `System Alerts`: service failure and recovery transitions.
- Local journal: every check-state transition and operator action.
- Telegram `System Logs` topic: optional silent audit copies, not required for correct
  operation.

Do not emit repeated alerts while a target remains in the same state.

## Durable State

Minimum `KaosController` state:

```json
{
  "telegram": {
    "systemMessageId": 0
  },
  "targets": {
    "kaos": {
      "state": "green",
      "consecutiveFailures": 0,
      "changedAt": ""
    }
  },
  "actions": {
    "nonces": {},
    "cooldowns": {}
  }
}
```

`KaosTelegram` stores the same shape independently with
`servicesMessageId`, service states, restart nonces, and restart cooldowns.
Neither health worker stores state in Brain PostgreSQL.

Write state atomically and keep it small. Health history belongs in the system
journal or a later monitoring database, not in Brain PostgreSQL.

## Delivery Plan

1. Keep Brain's Telegram delivery limited to application notifications, logs,
   and archives.
2. Create `KaosController` on the Control Center with read-only machine checks
   and the persistent System Status message.
3. Add `KaosController` machine-transition Telegram alerts.
4. Add manual WOL for a single non-PACS test target, then add approved hosts.
5. Create `KaosTelegram` on production with local service checks and the
   persistent Services Status message.
6. Add `KaosTelegram` service-transition Telegram alerts.
7. Add the restricted local service-control command.
8. Enable restart buttons for one low-risk service and verify confirmation,
   cooldown, audit, and recovery behavior.
9. Expand the restart allowlist incrementally.
10. Add hardware and backup checks after their underlying tools/storage are
    ready.

## Acceptance Criteria

- A normal poll by each health worker edits its existing Telegram message and
  sends no new message.
- Deleting either dashboard message causes only that message to be recreated.
- One transient timeout does not mark a target red.
- A confirmed outage generates one pushed Telegram alert and one later recovery alert.
- WOL is unavailable for green, yellow, service-only, or unknown states.
- Confirmation disappears after ten seconds and cannot be reused.
- An unauthorized Telegram account cannot invoke any action.
- A failed restart cannot enter an automatic restart loop.
- PACS, DICOM storage, PACS PostgreSQL, and KaosEghis have no restart action.
- Complete Brain, `KaosTelegram`, or production-host failure is still visible
  through the independent `KaosController` System Status message.
