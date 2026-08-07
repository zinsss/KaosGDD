# Brain Faxmail Architecture

Brain owns the faxmail automation workflow. KaosGDD UI does not expose a
separate fax utility, and the old temporary `KaosFaxMail` repo is not the
long-term product boundary.

Target shape:

```text
Roundcube / hosted mailbox = fax UI
Brain faxmail worker       = policy and automation
HylaFAX                    = modem authority
ntfy/webpush               = alerts
KaosGDD UI                 = not in the fax path
```

## Decisions

- Do not build a second fax inbox in KaosGDD.
- Do not keep a separate Postgres-backed KaosFaxMail app.
- Do not self-host a full mail server just for fax.
- Use a hosted mailbox for the human workflow.
- Use Roundcube as the fax tray.
- Use Brain as the invisible worker.
- Preserve the current custom HylaFAX host behavior.

## Mailboxes

Minimum:

```text
fax@kaosgdd.net       = human mailbox opened in Roundcube
fax-send@kaosgdd.net  = outgoing request address or alias
```

Optional aliases:

```text
fax-in@kaosgdd.net      -> fax@kaosgdd.net
fax-failed@kaosgdd.net  -> fax@kaosgdd.net
```

Brain distinguishes messages by recipient headers, folders, subject, and
validation rules. It must not trust only the visible `From:` header.

## Incoming Fax

```text
HylaFAX receives TIFF
  -> FaxDispatch resolves TIFF path
  -> incoming-mail script converts TIFF to PDF
  -> SMTP submission sends PDF to fax@kaosgdd.net
  -> Roundcube shows it
  -> Brain optionally sends ntfy/webpush
```

Incoming fax does not need a KaosGDD database row. The mailbox is the operational
paper trail, and HylaFAX `recvq` remains the modem-side source artifact.

## Outgoing Fax

Accepted outgoing request:

```text
To: fax-send@kaosgdd.net
Subject: fax:0548209762
Attachment: exactly one PDF
```

Brain worker flow:

```text
poll mailbox/folder
  -> validate authorized sender
  -> parse fax number
  -> require exactly one valid PDF
  -> extract PDF to worker temp storage
  -> convert PDF to fax-ready TIFF
  -> call sendfax
  -> reconcile HylaFAX doneq
  -> move mail to Processed / Rejected / Failed
  -> send notification or reply
```

Important: Brain should submit TIFF to HylaFAX, not raw PDF. The current modem
host has historical failed jobs with `Error: /undefinedfilename`, which points
back to HylaFAX-side PDF conversion problems.

## Current Modem Host Facts

The current host snapshot from `kaos`:

- modem device: `ttyACM0`
- USB modem: Conexant/Rockwell `0572:1340`
- HylaFAX version: `6.0.7`
- custom service: `kaos-hylafax-daemons.service`
- active receive hook: `/var/spool/hylafax/etc/FaxDispatch`
- active modem config: `/var/spool/hylafax/etc/config.ttyACM0`
- ECM disabled in modem config

Treat these as production behavior to preserve. Do not regenerate the modem
config from package defaults.

## Brain Module Boundary

Future code should live under Brain with a narrow module boundary, for example:

```text
apps/brain/services/faxmail/
```

Expected components:

- IMAP poller
- message/folder classifier
- outbound validator
- PDF attachment extractor
- PDF-to-TIFF converter
- HylaFAX client
- doneq reconciler
- notification adapter

This module should be operationally boring. Its job is to check the paperwork,
operate the modem, and move messages to the right folder.
