# ntfy Notification Routing

KaosGDD uses audience topics for normal notifications and one shared topic for
operational failures.

| Topic | Subscribers | Content |
| --- | --- | --- |
| `kaosgdd-ios` | iPhone and iPad | Normal notifications except calendar and task reminders |
| `kaosgdd-desktop` | Desktop clients | Normal notifications, including calendar and task reminders |
| `kaosgdd-system` | All managed clients | Fax delivery failures, server faults, and backup failures |

Successful incoming-fax notifications are published to both audience topics.
Mailbox-delivery failures are published only to the system topic.

Incoming-fax and selected-mail notifications include two actions:

- `Open` opens `https://mail.kaosgdd.net/`.
- `Later` opens a signed Brain action and schedules the same notification for
  delivery one hour later. Repeated taps update the same scheduled message.

Configure the signed action with:

```text
NOTIFICATION_LATER_SECRET=<random 32-byte-or-longer secret>
NOTIFICATION_LATER_BASE_URL=https://kaosgdd.net/api/notifications/later
NOTIFICATION_LATER_DELAY=1h
NOTIFICATION_LATER_TOKEN_TTL_SECONDS=604800
```

The later-action route must proxy to Brain and remain behind Cloudflare Access.
The notification carries a signed replay payload, never the ntfy API token.

The self-hosted ntfy server requires this setting for immediate iOS delivery:

```yaml
upstream-base-url: "https://ntfy.sh"
```

The upstream receives an opaque poll request. The iOS client retrieves the
notification from `ntfy.kaosgdd.net`.

## Client Subscriptions

iOS clients subscribe to:

```text
kaosgdd-ios
kaosgdd-system
```

Desktop clients subscribe to:

```text
kaosgdd-desktop
kaosgdd-system
```

Keep the old `kaosgdd` ACL during migration. Remove it only after both clients
receive their audience test message and the system test message.
