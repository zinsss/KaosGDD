# Faxmail Operations

HylaFAX owns modem transport, the hosted mailbox/Roundcube owns the human fax
inbox, and Brain owns push notifications. KaosGDD UI is not in the fax path.

## Production Workflow

```text
Conexant/Rockwell 0572:1340 on /dev/ttyACM0 (USB 2.0)
  -> faxgetty@ttyACM0 receives TIFF into /var/spool/hylafax/recvq
  -> /var/spool/hylafax/bin/faxrcvd
  -> TIFF-to-PDF sender submits through hosted SMTP
  -> hosted mailbox / Roundcube
  -> Brain observes stable recvq files and mailbox-delivery failures
  -> ntfy push
```

Do not regenerate the working modem configuration casually. Incoming fax is
production clinic transport.

## Source Of Truth

Maintained files are under:

```text
/srv/projects/KaosGDD/ops/faxmail
```

Live paths:

```text
/etc/hylafax/config.ttyACM0
/etc/hylafax/hfaxd.systemd.conf
/etc/kaosgdd/faxmail.env
/var/spool/hylafax/bin/faxrcvd
/usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py
/var/spool/hylafax/status/kaosgdd-faxmail/{sent,failed}
/var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
```

The Debian package invokes `bin/faxrcvd` directly on this host. `FaxDispatch`,
`hylafax-core.service`, and `kaos-hylafax-daemons.service` are not part of the
production workflow.

## Services

Package services:

```text
hylafax.service
faxq.service
hfaxd.service
faxgetty@ttyACM0.service
```

Kaos maintenance units:

```text
kaos-faxmail-retry.timer
kaos-hylafax-backup.timer
kaos-faxmail-retention.timer
```

`hylafax.service` must be enabled because `faxq` and `hfaxd` are its child
units. `faxgetty@ttyACM0.service` is enabled separately.

Install or repair the maintained host integration:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/install-host-maintenance.sh --install
```

This command does not restart `faxgetty` or alter the modem baseline. It:

- protects the custom `faxrcvd` with a dpkg diversion
- installs durable delivery state and a five-minute retry timer
- binds `hfaxd` to localhost and disables unused SNPP port 444
- enables the HylaFAX parent service at boot
- installs faxmail log rotation
- enables a daily local recvq backup
- deletes successfully emailed local TIFF and backup copies after 30 days
- verifies the resulting host state

## Mailbox Configuration

`/etc/kaosgdd/faxmail.env` is `root:uucp 0640` and stays outside Git.

Required variables:

```text
FAXMAIL_SMTP_HOST=
FAXMAIL_SMTP_PORT=587
FAXMAIL_SMTP_STARTTLS=true
FAXMAIL_SMTP_SSL=false
FAXMAIL_SMTP_USER=
FAXMAIL_SMTP_PASSWORD=
FAXMAIL_FROM=
FAXMAIL_TO=
FAXMAIL_SUBJECT_PREFIX=Incoming fax
FAXMAIL_STATE_DIR=/var/spool/hylafax/status/kaosgdd-faxmail
```

Use either STARTTLS or implicit SSL, never both. Keep the SMTP password out of
inventory archives and backups.

## Delivery State And Retry

Successful deliveries create:

```text
/var/spool/hylafax/status/kaosgdd-faxmail/sent/COMMID.json
```

Failures create:

```text
/var/spool/hylafax/status/kaosgdd-faxmail/failed/COMMID.json
```

The retry timer retries indefinitely with bounded backoff. Brain sends an
urgent ntfy alert when a failed marker first appears. A sent marker prevents a
manual hook replay from sending the same fax twice.

Inspect pending failures:

```bash
sudo find /var/spool/hylafax/status/kaosgdd-faxmail/failed \
  -maxdepth 1 -name '*.json' -type f -print
sudo systemctl start kaos-faxmail-retry.service
sudo journalctl -u kaos-faxmail-retry.service -n 50 --no-pager
```

## Historical Replay

Mark a fax already confirmed in the mailbox without sending it:

```bash
sudo -u uucp env FAXMAIL_STATE_DIR=/var/spool/hylafax/status/kaosgdd-faxmail \
  /usr/bin/python3 /usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py \
  /var/spool/hylafax/recvq/fax000000001.tif \
  --commid 000000001 --device ttyACM0 --mark-sent
```

Replay an undelivered fax through the normal idempotent hook:

```bash
sudo -u uucp /bin/sh /var/spool/hylafax/bin/faxrcvd \
  recvq/fax000000001.tif ttyACM0 000000001 ""
```

Use sender `--force` only when an intentional duplicate email is required.

## Brain Notifications

Production Brain mounts `/var/spool/hylafax` read-only. Important settings:

```text
FAX_NOTIFY_ENABLED=true
FAX_NOTIFY_RECVQ=/integrations/hylafax/recvq
FAX_NOTIFY_XFERFAXLOG=/integrations/hylafax/log/xferfaxlog
FAX_NOTIFY_STATE_PATH=/data/faxmail/notified-recvq.json
FAX_NOTIFY_DELIVERY_FAILURE_ROOT=/integrations/hylafax/status/kaosgdd-faxmail/failed
FAX_NOTIFY_MIN_FILE_AGE_SECONDS=60
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true
NTFY_URL=
NTFY_TOPIC_IOS=kaosgdd-ios
NTFY_TOPIC_DESKTOP=kaosgdd-desktop
NTFY_TOPIC_SYSTEM=kaosgdd-system
```

The minimum file age prevents notification while HylaFAX may still be writing
the TIFF. Routine incoming-fax notices use both audience topics;
mailbox-delivery failures use `kaosgdd-system`. Check `/api/brain/status` under
`faxmailNotifications` for enabled,
configured, lastError, failureCount, and minimumFileAgeSeconds.

## Verification

Run the non-destructive verifier:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/verify-hylafax-modem-ready.sh ttyACM0
```

Expected essentials:

```text
hylafax, faxq, hfaxd, and faxgetty active
hylafax and faxgetty enabled
hfaxd listening only on 127.0.0.1:4559
port 444 closed
faxrcvd and sender matching maintained source
no pending mailbox delivery failures
modem Running and idle
```

Watch a live receive:

```bash
sudo journalctl -u faxgetty@ttyACM0.service -f
sudo tail -f /var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
```

Confirm all three results: TIFF in `recvq`, PDF in the mailbox, and ntfy push.

## Backup And Retention

The daily timer copies received TIFFs and non-secret active configuration into:

```text
/srv/kaos/backups/faxmail
```

Run immediately:

```bash
sudo systemctl start kaos-hylafax-backup.service
sudo cat /srv/kaos/backups/faxmail/current/status.txt
```

This is local staging, not disaster recovery. Sync it to encrypted Synology
storage when the backup target is ready. The backup script never copies
`/etc/kaosgdd/faxmail.env`.

The daily retention timer removes both copies of a received TIFF after 30 days
only when its durable `sentAt` marker confirms successful SMTP submission. It
never removes a fax with a failed marker, an unrecognized path, or no sent
marker. The small sent marker remains and records `purgedAt` for audit and
idempotency.

Preview current eligibility without deleting anything:

```bash
sudo /usr/bin/python3 \
  /usr/local/lib/kaosgdd/faxmail/cleanup-received-faxes.py \
  --retention-days 30 --dry-run
```

Run the policy immediately:

```bash
sudo systemctl start kaos-faxmail-retention.service
```

The hook log rotates daily for 30 days. HylaFAX rotates `xferfaxlog` separately.

## Inventory

```bash
sudo ./ops/faxmail/inventory-hylafax-host.sh \
  /srv/kaos/backups/hylafax/inventory-$(date +%Y%m%d-%H%M%S)
```

Inventory output is mode `0600`. It captures secret file metadata and variable
names, not credential values or `hosts.hfaxd` contents.

## Package Upgrade And Rollback

The dpkg diversion keeps package upgrades from overwriting the custom receive
hook. Verify after a HylaFAX upgrade with the standard verifier.

To intentionally return to package `faxrcvd`:

```bash
sudo ./ops/faxmail/restore-mailbox-faxrcvd.sh --restore-package
```

Do not restart `faxgetty` for a hook-only update. Restart it only for modem or
device configuration changes.

## Outgoing Fax

Outgoing fax automation is not enabled yet. Before implementing it, confirm the
actual international dialing prefix and full local fax identity. Convert PDFs
to fax-ready TIFF before submitting to HylaFAX.
