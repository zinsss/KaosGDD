# Brain Faxmail Architecture

Brain owns the faxmail automation workflow. KaosGDD UI does not expose a
separate fax utility, and the old temporary `KaosFaxMail` repo is not the
long-term product boundary.

Target shape:

```text
Telegram Fax topic         = outgoing fax request interface
Brain faxmail worker       = policy and automation
HylaFAX                    = modem authority
Telegram Notifications    = normal fax alerts
Telegram System Alerts    = fax failures
Telegram Fax              = sent/received fax document archive
KaosGDD UI                 = not in the fax path
```

## Decisions

- Do not build a second fax inbox in KaosGDD.
- Do not keep a separate Postgres-backed KaosFaxMail app.
- Do not self-host a full mail server just for fax.
- Use Telegram for the human outgoing workflow; do not poll IMAP for fax jobs.
- Use Brain as the invisible worker.
- Preserve the current custom HylaFAX host behavior.
- Upload only confirmed sent and received fax documents to the private
  Telegram Fax topic; HylaFAX remains transport authority.

## Incoming Fax

```text
HylaFAX receives TIFF
  -> Brain polls stable files in HylaFAX recvq directly
  -> Brain reads caller/time metadata from xferfaxlog
  -> Brain converts TIFF to a temporary PDF
  -> Brain uploads only the renamed PDF to Telegram Fax
  -> Brain sends pushed Telegram notification
```

Incoming fax does not need a KaosGDD database row. HylaFAX `recvq` is the
modem-side source artifact and Telegram is the human archive. Incoming archive
delivery does not poll IMAP. Telegram names
the document `YYYY-MM-DD-HH:MM_FROM_fax-number.pdf` using KST, and receives no
caption alongside it. The source TIFF remains subject to the 30-day retention
policy. The retention worker deletes a TIFF and its local backup only after the
Telegram archive state confirms upload and the 30-day window has elapsed.

## Outgoing Fax

Accepted outgoing request in the private Telegram `Fax` topic:

```text
Document: exactly one PDF
Desktop: caption the PDF with fax:0548209762
Mobile: upload the PDF, then reply directly to it with fax:0548209762
```

Brain worker flow:

```text
poll Telegram Bot API directly
  -> require configured supergroup and Fax topic
  -> parse fax number
  -> require exactly one valid PDF
  -> download and validate the PDF with a strict size limit
  -> convert PDF to fax-ready TIFF
  -> call sendfax
  -> reconcile HylaFAX doneq
  -> send lifecycle notification
  -> archive the confirmed sent PDF to Telegram
  -> remove the user's upload, command, and bot instruction messages
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

Queued, sending, and sent use the Telegram Notifications topic. Failed
transmission uses the Telegram System Alerts topic.

After `doneq` confirms success, the Telegram archive worker uploads the original
outgoing PDF. Queued, sending, and failed jobs never upload a document. Archive
state stores only Telegram message metadata and idempotency keys, not another
copy of the fax.

## Telegram Boundary

Brain long-polls Telegram directly; there is no public webhook. It accepts a
PDF only from the configured supergroup and numeric Fax topic ID. Desktop can
use a caption matching `fax:<number>`; mobile can reply directly to an
uncaptioned PDF with the same text. An uncaptioned PDF and a standalone fax
number are inert independently. Private chats, other groups, other topics,
malformed numbers, non-PDF data, oversized files, and duplicate Telegram
message/file identities cannot create a second fax job. The bot token stays in
the production Brain secret env file.

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

- Telegram topic intake
- HylaFAX recvq scanner
- xferfaxlog metadata parser
- outbound validator
- incoming TIFF-to-PDF converter
- PDF-to-TIFF converter
- HylaFAX client
- doneq reconciler
- notification adapter

This module should be operationally boring. Its job is to check the paperwork,
operate the modem, and move messages to the right folder.
