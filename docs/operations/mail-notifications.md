# Mail Notifications

KaosGDD Brain polls selected IMAP folders and publishes pushed new-mail
summaries to the Telegram topic:

```text
Notifications
```

The notification worker does not store message bodies or attachments. Its
durable state contains mailbox UIDVALIDITY values and the last processed UID
only.

An independently checkpointed Telegram archive worker can fetch new
Naver messages from the same selected folders. It posts this summary and then
uploads each attachment as a Telegram document:

```text
Naver Mail >> {folder}
From: {sender}

{subject}

Attachments
1. {filename}
2. {filename}

{first 15 lines of plain-text preview}
```

The attachment section is omitted when a message has no attachments.

The worker selects mailboxes read-only and fetches messages with
`BODY.PEEK[]`, so archiving does not mark mail as read. It prefers the
`text/plain` MIME body and converts HTML to plain text only when no plain body
exists. Temporary or permanent copies of message bodies and attachment data
are not written to disk.

## Rules

Naver watches `각종공문`, `세무사`, and all descendant folders under either
root. Fax is not an IMAP mail-notification source; Telegram handles outgoing
fax requests directly and HylaFAX reports incoming and transmission state.

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

TELEGRAM_BOT_TOKEN=
TELEGRAM_SUPERGROUP_CHAT_ID=
TELEGRAM_TOPIC_MAIL_ID=
MAIL_TELEGRAM_ARCHIVE_ENABLED=true
```

The worker posts to the `Mail` forum topic. The legacy
`MAIL_TELEGRAM_ARCHIVE_CHAT_ID` and `MAIL_TELEGRAM_ARCHIVE_TOPIC_ID` variables
remain supported as per-worker overrides. The default attachment limit is 20
MB. Oversized and empty attachments are named in the summary but not uploaded.

The first successful scan establishes a checkpoint without uploading existing
mail. Set `MAIL_TELEGRAM_ARCHIVE_MARK_EXISTING_ON_FIRST_RUN=false` only for an
intentional historical import. Summary and attachment progress is saved
separately, preventing a failed attachment retry from reposting an already
successful summary.

Enable and restart one account at a time. Verify its entry under
`mailNotifications.accounts` in `/api/brain/status` before enabling the next.
The Telegram worker appears separately as `mailTelegramArchive`. Archive
messages and attachments in `Mail` are silent; the short message in
`Notifications` is the single pushed alert.

## Production Storage

```text
/srv/kaos/data/kaosgdd/brain/mail -> /data/mail
```

The worker polls every 60 seconds by default. Mail remains authoritative on the
provider IMAP server; KaosGDD does not host a webmail client.
