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
  -> bin/faxrcvd resolves TIFF path
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

The transport boundary is a separate unprivileged `fax-bridge` container.
Brain writes a versioned manifest and PDF SHA-256 to a shared queue. The bridge
validates both, performs PDF-to-TIFF conversion, and is the only application
component allowed to contact localhost `hfaxd`. It defaults to dry-run and has
no public listener. Brain mounts the HylaFAX spool read-only solely to reconcile
`doneq` results.

Current rollout modes:

- `shadow`: parse and record validation results without writing attachments.
- `dry-run`: queue, convert, and verify TIFF without calling `sendfax`.
- `live`: submit the verified TIFF and reconcile the resulting HylaFAX job.

Both Brain and the bridge have independent mode switches. This deliberately
requires two configuration changes before a live transmission is possible.

In live mode, Brain records and publishes each transition once:

```text
queued -> sending (HylaFAX job assigned) -> sent (doneq confirms success)
                                      `-> failed (terminal error)
```

Queued, sending, and sent use the normal desktop/iOS notification audiences.
Failed transmission uses the system topic.

Important: Brain should submit TIFF to HylaFAX, not raw PDF. The current modem
host has historical failed jobs with `Error: /undefinedfilename`, which points
back to HylaFAX-side PDF conversion problems.

## Current Modem Host Facts

The current host snapshot from `kaos`:

- modem device: `ttyACM0`
- USB modem: Conexant/Rockwell `0572:1340`
- HylaFAX version: `6.0.7`
- package services: `hylafax`, `faxq`, `hfaxd`, and `faxgetty@ttyACM0`
- active receive hook: `/var/spool/hylafax/bin/faxrcvd`
- active modem config: `/var/spool/hylafax/etc/config.ttyACM0`
- ECM disabled in modem config

Treat these as production behavior to preserve. Do not regenerate the modem
config from package defaults.

## Legacy KaosGdd-web Lessons

Before implementing or moving fax behavior, check the archived legacy repo:

```text
/srv/projects/_archive/KaosGdd-web-archived-20260806-121403
```

Key legacy references:

```text
docs/fax-hylafax-operations.md
docs/fax-settings.md
ops/hylafax/README.md
ops/hylafax/faxrcvd.kaosgdd-working
ops/hylafax/kaosgdd-faxrcvd.working
ops/hylafax/install-kaosgdd-hylafax-hooks.sh
ops/backup/kaosgdd-backup.sh
backend/scripts/hylafax_recv_hook.py
backend/app/engine/fax_service.py
backend/app/engine/fax_pdf_conversion_service.py
backend/tests/test_fax_v0.py
```

Preserve these legacy decisions in the Brain worker:

- HylaFAX is transport authority, not application state authority.
- PDF remains the human/mailbox artifact.
- Outgoing fax should be converted to fax-ready TIFF before `sendfax`.
- Do not allow HylaFAX host-side PDF conversion to become the normal path.
- Parse HylaFAX `doneq` files for status with `statuscode`, `state`, and
  `returned`.
- Treat `Error: /undefinedfilename` as a regression signal that PDF conversion
  leaked back into HylaFAX spool handling.
- Handle `sendfax command not found` and `sendfax command timed out` as normal
  operational errors, not crashes.
- Find the active `hosts.hfaxd`; package paths vary.
- Use explicit no-password client rules with `:::` if `hfaxd` prompts for
  `PASS`.
- Back up HylaFAX hooks and config before edits.

The live `kaos` host invokes `/var/spool/hylafax/bin/faxrcvd` directly. Older
`FaxDispatch` and custom-daemon instructions are archived legacy behavior and
must not be applied to production.

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
