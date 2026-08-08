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
