# Telegram-First Kaos Workflows

## Decision

Telegram is the default human inbox and action surface for custom Kaos
workflows. It replaces small bespoke inboxes where Telegram already supplies a
reliable feed, file transfer, mobile notifications, topics, and inline actions.

This does not replace authoritative services:

| Domain | Authority | Telegram role |
| --- | --- | --- |
| Documents | Paperless-ngx | intake and routing |
| PDF processing | Stirling-PDF | handoff and result delivery |
| HWP conversion | RHWP | handoff and result delivery |
| Memos | Memos | read-only personal archive |
| Calendar and tasks | Radicale | notifications and quick actions only |
| Fax | HylaFAX | intake, archive, and send command surface |
| Passwords | Vaultwarden | none |
| Medical images | KaosPACS | none |

Brain remains the automation and adapter layer. It may retain offsets, job
status, deduplication keys, and expiring working files. It must not become a
second permanent store for documents, memos, calendar data, tasks, or faxes.

## Telegram Topics

The private KaosGDD supergroup is divided by workflow. Topic IDs are deployment
configuration and are never inferred from topic names.

- `System Controller`: control actions owned by KaosTelegram and KaosController.
- `System Alerts`: pushed infrastructure failures and recoveries.
- `System Logs`: quiet operational history.
- `Notifications`: general user notifications.
- `Fax`: received and sent fax archive plus outgoing fax input.
- `Mail`: selected mailbox archive.
- `Memos`: read-only personal Memos archive.
- `Documents`: temporary document intake and routing.

## Documents Workflow

The first Documents implementation accepts PDFs only:

```text
Telegram Documents topic
        |
        v
Brain validates and downloads the PDF
        |
        v
expiring document queue
        |
        +--> Open
        +--> Paperless-ngx consume directory
        +--> Delete temporary copy
```

The original Telegram upload remains in the topic. The Brain copy expires under
the existing document-retention policy. Paperless becomes authoritative only
after the user selects the Paperless action.

RHWP and Stirling remain separate services. Later Telegram actions may submit
to their documented interfaces, but their conversion logic does not belong in
Brain.

The current KaosGDD document inbox remains available during verification. It
can be removed after Telegram intake, preview, Paperless handoff, deletion,
expiry, and duplicate protection have been exercised in production.

## Bot API Ownership

Brain uses one `getUpdates` consumer for the KaosGDD bot token. Fax intake,
Memos-topic protection, Documents intake, and future callbacks must be
dispatched through that consumer because Telegram update offsets are shared.

The bot is restricted to one configured private supergroup and explicit topic
IDs. User actions outside those boundaries are ignored.

The official self-hosted Telegram Bot API may run on `kaos` to support files
above the hosted Bot API download limit. It is infrastructure, not another bot.
Brain keeps the application logic and changes only its Bot API base URL. The
service is private, has persistent storage, and is never exposed through
Cloudflare.

## New Workflow Rule

Before building a custom Kaos page:

1. Use an existing authoritative service when it owns the domain well.
2. Use Telegram for a custom human inbox, notification feed, file handoff, or
   small command surface.
3. Add a KaosGDD page only when the workflow needs richer interaction than
   Telegram can provide efficiently.
4. Keep permanent records in the authoritative service and keep Brain state
   minimal and expiring.
