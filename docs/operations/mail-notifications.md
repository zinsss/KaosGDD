# Mail Notifications

KaosGDD Brain polls selected IMAP folders and publishes new-mail summaries to
both normal audience topics:

```text
kaosgdd-ios
kaosgdd-desktop
```

It does not store message bodies or attachments. The durable state contains
mailbox UIDVALIDITY values and the last processed UID only.

## Rules

Naver watches `각종공문`, `세무사`, and all descendant folders under either
root. Gmail watches `INBOX` and
notifies only when the From, To, Cc, or Reply-To headers contain one of:

```text
fax@kaosgdd.net
fax-in@kaosgdd.net
fax-send@kaosgdd.net
fax-failed@kaosgdd.net
```

Successful mailbox login establishes the first checkpoint without sending old
mail notifications. A changed UIDVALIDITY also establishes a fresh checkpoint
for that mailbox.

## Credentials

Credentials belong in `/srv/kaos/secrets/kaosgdd-brain.env`, which must remain
mode `0600`. Use IMAP-specific or app passwords rather than primary account
passwords where the provider supports them.

```text
MAIL_NOTIFY_NAVER_USERNAME=
MAIL_NOTIFY_NAVER_PASSWORD=
MAIL_NOTIFY_NAVER_FOLDERS=각종공문,세무사
MAIL_NOTIFY_NAVER_ENABLED=true

MAIL_NOTIFY_GMAIL_USERNAME=yhshfm@gmail.com
MAIL_NOTIFY_GMAIL_PASSWORD=
MAIL_NOTIFY_GMAIL_ENABLED=true
```

Enable and restart one account at a time. Verify its entry under
`mailNotifications.accounts` in `/api/brain/status` before enabling the next.

## Production Storage

```text
/srv/kaos/data/kaosgdd/brain/mail -> /data/mail
```

The worker polls every 60 seconds by default. Notification clicks open
`https://mail.kaosgdd.net/`.
