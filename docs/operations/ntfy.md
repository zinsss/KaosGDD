# ntfy Notification Routing

KaosGDD uses one topic per device class. Operational failures retain urgent
priority but use the same device topics, keeping one notification collection on
each client.

| Topic | Subscribers | Content |
| --- | --- | --- |
| `kaosgdd-ios` | iPhone and iPad | Mail, fax, and urgent operational notifications |
| `kaosgdd-desktop` | Desktop clients | Mail, fax, urgent operations, calendar, and tasks |

Successful incoming-fax notifications are published to both audience topics.
Mailbox-delivery failures and other operational faults are urgent and published
to both device topics.

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
```

Desktop clients subscribe to:

```text
kaosgdd-desktop
```

Keep the old `kaosgdd` ACL during migration. Remove it only after both clients
receive their device-topic test message. The retired `kaosgdd-system` topic can
be removed from client subscriptions and ACLs after deployment verification.
