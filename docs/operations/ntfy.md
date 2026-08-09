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

Notification action buttons are currently disabled globally:

```text
NOTIFICATION_ACTIONS_ENABLED=false
```

This removes Open and Later from fax, mail, and every other Brain notification.
The signed Later implementation remains available for a future opt-in. Enabling
it also requires:

```text
NOTIFICATION_ACTIONS_ENABLED=true
NOTIFICATION_LATER_SECRET=<random 32-byte-or-longer secret>
NOTIFICATION_LATER_BASE_URL=https://kaosgdd.net/api/notifications/later
NOTIFICATION_LATER_DELAY=1h
NOTIFICATION_LATER_TOKEN_TTL_SECONDS=604800
```

The Later route must proxy to Brain and remain behind Cloudflare Access. The
notification carries a signed replay payload, never the ntfy API token.

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
