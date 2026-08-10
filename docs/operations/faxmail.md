# Fax Operations

HylaFAX owns modem transport. Brain owns Telegram intake, notifications, and
document archival. There is no fax email path and KaosGDD UI is not in the fax
workflow.

## Production Workflow

```text
Incoming
Conexant/Rockwell 0572:1340 on /dev/ttyACM0 (USB 2.0)
  -> faxgetty@ttyACM0 stores TIFF in /var/spool/hylafax/recvq
  -> Brain reads recvq and xferfaxlog
  -> Brain sends a pushed Telegram notification
  -> Brain converts TIFF to PDF and uploads it to Telegram Fax

Outgoing
Telegram Fax PDF + fax:<number>
  -> Brain validates and queues the PDF
  -> fax-bridge converts PDF to fax-ready TIFF
  -> HylaFAX sends through /dev/ttyACM0
  -> Brain reconciles doneq and sends lifecycle notifications
  -> confirmed sent PDF is archived to Telegram Fax
```

Do not regenerate the working modem configuration casually. The USB modem must
remain on USB 2.0.

## Source Of Truth

Maintained files:

```text
/srv/projects/KaosGDD/ops/faxmail
/srv/projects/KaosGDD/apps/brain/services/faxmail
```

Important live paths:

```text
/etc/hylafax/config.ttyACM0
/etc/hylafax/hfaxd.systemd.conf
/var/spool/hylafax/bin/faxrcvd
/var/spool/hylafax/recvq
/var/spool/hylafax/doneq
/var/spool/hylafax/log/xferfaxlog
/srv/kaos/data/kaosgdd/brain/faxmail/telegram-archive.json
/srv/kaos/data/kaosgdd/brain/fax-outgoing
```

`faxrcvd` is intentionally a no-mail hook. HylaFAX has already persisted the
TIFF before invoking it; Brain discovers received faxes by polling `recvq`.

## Services

```text
hylafax.service
faxq.service
hfaxd.service
faxgetty@ttyACM0.service
kaos-hylafax-backup.timer
kaos-faxmail-retention.timer
kaosgdd-brain
kaosgdd-fax-bridge
```

Install or repair the maintained host integration only when no outgoing fax is
active:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/install-host-maintenance.sh --install
```

The installer does not restart `faxgetty` or alter the modem baseline. It:

- installs the Telegram-only `faxrcvd` hook
- binds `hfaxd` to localhost and disables unused SNPP port 444
- refreshes `faxq` and `hfaxd` after configuration changes
- enables a daily local `recvq` backup
- enables Telegram-gated 30-day retention
- verifies scheduler and modem readiness

## Brain Configuration

Production Brain mounts `/var/spool/hylafax` read-only. Secrets remain in
`/srv/kaos/secrets/kaosgdd-brain.env`.

```text
FAX_NOTIFY_ENABLED=true
FAX_NOTIFY_RECVQ=/integrations/hylafax/recvq
FAX_NOTIFY_XFERFAXLOG=/integrations/hylafax/log/xferfaxlog
FAX_NOTIFY_STATE_PATH=/data/faxmail/notified-recvq.json
FAX_NOTIFY_MIN_FILE_AGE_SECONDS=60
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true

FAX_TELEGRAM_ARCHIVE_ENABLED=true
FAX_TELEGRAM_ARCHIVE_RECVQ=/integrations/hylafax/recvq
FAX_TELEGRAM_ARCHIVE_XFERFAXLOG=/integrations/hylafax/log/xferfaxlog
FAX_TELEGRAM_ARCHIVE_STATE_PATH=/data/faxmail/telegram-archive.json
FAX_TELEGRAM_ARCHIVE_MIN_FILE_AGE_SECONDS=60

FAX_OUTGOING_ENABLED=true
FAX_OUTGOING_MODE=live
FAX_OUTGOING_QUEUE_ROOT=/data/fax-outgoing
FAX_OUTGOING_STATE_PATH=/data/fax-outgoing/state.json
FAX_OUTGOING_DONEQ_ROOT=/integrations/hylafax/doneq

TELEGRAM_FAX_INTAKE_ENABLED=true
TELEGRAM_FAX_DELETE_SOURCE_ON_SUCCESS=true
TELEGRAM_BOT_TOKEN=
TELEGRAM_SUPERGROUP_CHAT_ID=
TELEGRAM_TOPIC_FAX_ID=
TELEGRAM_TOPIC_NOTIFICATIONS_ID=
TELEGRAM_TOPIC_SYSTEM_ALERTS_ID=
```

The first run marks existing files as seen when the corresponding
`MARK_EXISTING_ON_FIRST_RUN` setting is true.

## Incoming Archive

Brain uploads received faxes silently to the private Telegram Fax topic as:

```text
YYYY-MM-DD-HH:MM_FROM_fax-number.pdf
```

The temporary conversion PDF is removed after upload. HylaFAX TIFF remains the
local source artifact until retention.

## Outgoing Intake

```text
Desktop: caption the PDF with fax:022848302
Mobile: upload the PDF, then reply directly with fax:022848302
```

The `fax:` prefix is mandatory. Private chats, other groups/topics, malformed
numbers, non-PDF data, oversized documents, and duplicate source identities do
not create a job.

After HylaFAX confirms success, Brain deletes:

- the user's source PDF message
- the bot's reply instruction
- the user's `fax:<number>` reply

Failed jobs retain those messages for retry or diagnosis. The server job copy
and Telegram sent-fax archive remain.

Sent archive captions contain only the destination and KST completion time:

```text
Sent fax.
: to 022848302
: 2026-08-03 13:03
```

## Retention

`kaos-faxmail-retention.timer` runs daily. It deletes a received TIFF and its
local backup after 30 days only when
`/srv/kaos/data/kaosgdd/brain/faxmail/telegram-archive.json` records the item as
`status: uploaded`. Missing, invalid, recent, or `baselined` records fail closed
and preserve the files.

```bash
sudo systemctl start kaos-faxmail-retention.service
sudo journalctl -u kaos-faxmail-retention.service -n 50 --no-pager
```

## Verification

```bash
faxstat -s
systemctl is-active faxgetty@ttyACM0.service faxq.service hfaxd.service
docker ps --filter name=kaosgdd-brain --filter name=kaosgdd-fax-bridge
curl -fsS http://100.94.208.16:8092/api/brain/status
```

Expected modem state:

```text
HylaFAX scheduler on kaos: Running
Modem ttyACM0 (+82 54): Running and idle
```

If the modem is missing, check `/dev/ttyACM0` and USB 2.0 before changing
HylaFAX configuration.

## Korean PDF Rendering

Some PDFs reference Korean CID fonts without embedding them. The fax bridge
image includes `fonts-nanum`, and its Docker build asserts that
`NanumMyeongjo.ttf` exists. Keep that package when rebuilding the bridge or
Korean text may render incorrectly in the fax TIFF.
