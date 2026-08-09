# Faxmail Maintenance And Reproduction Playbook

This playbook is the practical rebuild guide for KaosGDD incoming fax. It
documents the HylaFAX modem setup, hosted mail path, mailbox hook, and Brain
Pushover notifier needed to reproduce the working `kaos` system.

The current production goal is incoming fax only:

```text
USB fax modem
  -> HylaFAX
  -> /var/spool/hylafax/bin/faxrcvd
  -> TIFF to PDF helper
  -> Gmail SMTP
  -> Cloudflare Email Routing alias
  -> Gmail/Roundcube mailbox
  -> Brain polls recvq
  -> Pushover push
```

Outgoing fax by email is intentionally not part of this runbook yet.

## Current Known-Good State

Host:

```text
kaos
```

Modem:

```text
device: /dev/ttyACM0
USB ID: 0572:1340
USB name: Conexant Systems (Rockwell), Inc. CX93010 ACF Modem
recommended port: USB 2.0 direct port, not USB 3.0 or a hub
```

HylaFAX:

```text
version observed: 6.0.7
spool: /var/spool/hylafax
receive queue: /var/spool/hylafax/recvq
receive hook: /var/spool/hylafax/bin/faxrcvd
modem config: /var/spool/hylafax/etc/config.ttyACM0
mail hook log: /var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
```

Systemd units used by the Debian package:

```text
faxq.service
hfaxd.service
faxgetty@ttyACM0.service
hylafax.service
```

The old legacy host used a custom `kaos-hylafax-daemons.service`; this new
target host works with the packaged `faxq.service` and `hfaxd.service`.

## Required Packages

Install:

```bash
sudo apt update
sudo apt install -y hylafax-server hylafax-client ghostscript libtiff-tools
```

Required commands after install:

```bash
command -v faxstat
command -v sendfax
command -v faxq
command -v hfaxd
command -v faxgetty
command -v gs
command -v tiff2pdf
```

Expected HylaFAX spool paths:

```bash
sudo find /var/spool /var/lib /etc -maxdepth 4 \( \
  -name FaxDispatch -o \
  -name config -o \
  -name recvq -o \
  -name doneq -o \
  -name sendq -o \
  -name etc \
\) | grep -Ei 'hylafax|fax'
```

Expected useful paths:

```text
/var/spool/hylafax/config
/var/spool/hylafax/etc
/var/spool/hylafax/doneq
/var/spool/hylafax/sendq
/var/spool/hylafax/recvq
/etc/hylafax/config
```

## USB Modem Setup

Use a direct USB 2.0 port. This modem did not appear reliably through the tested
USB 3.0 path.

After plugging the modem in:

```bash
lsusb | grep -Ei 'conexant|rockwell|0572:1340|modem|fax'
ls -lah /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
dmesg | grep -Ei 'ttyACM|ttyUSB|cdc_acm|modem|usb' | tail -80
```

Expected:

```text
/dev/ttyACM0
Bus ... ID 0572:1340 Conexant Systems (Rockwell), Inc. CX93010 ACF Modem
```

If `/dev/ttyACM0` is missing, do not debug HylaFAX yet. Fix USB/device
visibility first.

## Modem Config Without Probing

`faxaddmodem ttyACM0` can hang during modem probing on this modem. Do not
repeatedly run it and hope for a different result.

If probing hangs:

```bash
sudo pkill -f faxaddmodem || true
```

Install the known-good baseline config:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/install-ttyacm0-baseline-config.sh
```

Important values preserved by the baseline:

```text
CountryCode:            82
AreaCode:               054
FAXNumber:              "+82 54"
RingsBeforeAnswer:      1
MaxRecvPages:           25
ModemType:              Class1
ModemRate:              38400
ModemFlowControl:       rtscts
Class1ECMSupport:       No
Class1PersistentECM:    No
Class1ECMFrameSize:     64
```

If `faxaddmodem` does complete and creates a full config, apply the known-good
overrides instead:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/apply-ttyacm0-known-good-baseline.sh
```

## HylaFAX Services

Start and enable the daemons:

```bash
sudo systemctl enable --now hylafax.service faxgetty@ttyACM0.service
```

`faxq.service` and `hfaxd.service` are children of `hylafax.service`; enabling
only the child units does not attach the parent to the boot target.

Check service state:

```bash
systemctl status faxq.service hfaxd.service hylafax.service faxgetty@ttyACM0.service --no-pager -l
ps -ef | grep -Ei '[f]axq|[h]faxd|[f]axgetty'
ss -tulpn | grep 4559 || true
faxstat -s
faxstat -r
```

Expected healthy output:

```text
HylaFAX scheduler on kaos: Running
Modem ttyACM0 (+82 54): Running and idle
```

If `faxgetty@ttyACM0.service` fails with `dev-ttyACM0.device`, the modem is not
visible as `/dev/ttyACM0`. Check USB again before changing HylaFAX config.

## Hosted Mail Design

The system avoids self-hosting mail. Cloudflare Email Routing receives aliases
on `kaosgdd.net` and forwards them into a hosted Gmail inbox.

Recommended addresses:

```text
fax@kaosgdd.net        main human fax mailbox alias
fax-in@kaosgdd.net     incoming fax delivery alias
fax-send@kaosgdd.net   future outgoing request alias
fax-failed@kaosgdd.net future failure/rejected alias
```

Current incoming path uses:

```text
FAXMAIL_TO=fax-in@kaosgdd.net
```

Cloudflare routes `fax-in@kaosgdd.net` to the actual destination Gmail account.
Gmail/Roundcube is the human UI.

Recommended Gmail labels/folders:

```text
Fax
Fax/Incoming
Fax/Processed
Fax/Rejected
Fax/Failed
Fax/Archive
```

Incoming fax delivery does not require these labels, but creating them makes the
mailbox ready for later Brain-managed outgoing/rejected states.

## Gmail SMTP Settings

HylaFAX does not use a local mail server in this setup. The receive hook runs a
Python SMTP sender using `/etc/kaosgdd/faxmail.env`.

Example:

```text
FAXMAIL_SMTP_HOST=smtp.gmail.com
FAXMAIL_SMTP_PORT=587
FAXMAIL_SMTP_STARTTLS=true
FAXMAIL_SMTP_SSL=false
FAXMAIL_SMTP_USER=actual-smtp-sender@gmail.com
FAXMAIL_SMTP_PASSWORD=google-app-password
FAXMAIL_FROM=actual-smtp-sender@gmail.com
FAXMAIL_TO=fax-in@kaosgdd.net
FAXMAIL_SUBJECT_PREFIX=Incoming fax
```

Rules:

- `FAXMAIL_FROM` should match `FAXMAIL_SMTP_USER` unless Gmail has that sender
  address configured and verified under "Send mail as".
- Prefer a sender Gmail account that is different from the Gmail account that
  Cloudflare routes into. Gmail can hide or deduplicate self-routed messages.
- Use a Google app password, not the normal Google login password.
- Keep `/etc/kaosgdd/faxmail.env` out of git.
- The live HylaFAX hook runs as `uucp`, so the env file must be readable by
  group `uucp`.

Permissions:

```bash
sudo chgrp uucp /etc/kaosgdd/faxmail.env
sudo chmod 0640 /etc/kaosgdd/faxmail.env
```

Show env without leaking the password:

```bash
sudo sh -c 'grep -n "^FAXMAIL_" /etc/kaosgdd/faxmail.env | sed "s/FAXMAIL_SMTP_PASSWORD=.*/FAXMAIL_SMTP_PASSWORD=REDACTED/"'
```

## Incoming Hook Installation

The working target host invokes:

```text
/var/spool/hylafax/bin/faxrcvd "recvq/fax000000001.tif" "ttyACM0" "000000001" ""
```

Therefore the live mailbox hook must be installed at:

```text
/var/spool/hylafax/bin/faxrcvd
```

Install:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/install-mailbox-faxrcvd.sh --install
```

The installer:

- backs up the existing `faxrcvd`
- installs a dpkg diversion so package upgrades cannot overwrite the hook
- installs `ops/faxmail/templates/faxrcvd.mailbox`
- copies the Python sender into `/usr/local/lib/kaosgdd/faxmail`
- prepares durable `sent` and `failed` delivery state
- prepares hook log permissions
- prepares `/etc/kaosgdd/faxmail.env` permissions when the file exists

Runtime paths after install:

```text
/var/spool/hylafax/bin/faxrcvd
/usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py
/var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
/etc/kaosgdd/faxmail.env
/var/spool/hylafax/status/kaosgdd-faxmail/{sent,failed}
```

Expected permissions:

```text
/var/spool/hylafax/bin/faxrcvd                         uucp:uucp 0755
/usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py root:uucp 0755
/var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log uucp:uucp 0640
/etc/kaosgdd/faxmail.env                               root:uucp 0640
```

Why the Python sender is copied outside the repo:

```text
/srv/projects/KaosGDD is private to user zin on production.
HylaFAX hooks run as uucp.
uucp cannot traverse a 0700 repo directory.
```

Manual `sudo` tests can pass while the live hook fails. Always test as `uucp`
when checking the live hook:

```bash
sudo -u uucp test -r /etc/kaosgdd/faxmail.env && echo env-ok
sudo -u uucp test -w /var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log && echo log-ok
sudo -u uucp test -x /usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py && echo script-ok
```

## Hook Tests

Process an already received fax. Delivery is idempotent by communication ID,
so an already delivered fax is skipped unless `--force` is explicitly used on
the Python sender:

```bash
sudo -u uucp /bin/sh /var/spool/hylafax/bin/faxrcvd \
  recvq/fax000000001.tif \
  ttyACM0 \
  000000001 \
  ""
```

Expected log:

```text
--- ... faxrcvd mailbox start ---
FILE_ARG=recvq/fax000000001.tif
DEVICE=ttyACM0
COMMID=000000001
SRC=/var/spool/hylafax/recvq/fax000000001.tif
REMOTE_NUMBER=unknown
sent incoming fax PDF to fax-in@kaosgdd.net: fax000000001.pdf
sender exit=0
--- ... faxrcvd mailbox end ---
```

Watch live receive:

```bash
sudo journalctl -u faxgetty@ttyACM0.service -f
```

In another terminal:

```bash
sudo tail -f /var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
```

A successful modem receive looks like:

```text
ANSWER: FAX CONNECTION DEVICE '/dev/ttyACM0'
RECV FAX (...): recvq/fax000000001.tif from example-sender
RECV FAX: bin/faxrcvd "recvq/fax000000001.tif" "ttyACM0" "000000001" ""
```

## Brain Pushover Notifications

Brain does not send the fax email. The HylaFAX hook sends the email. Brain
polls stable receive files and durable mailbox-delivery failures, then sends
push notifications through Pushover.

Brain environment:

```text
FAX_NOTIFY_ENABLED=true
FAX_NOTIFY_RECVQ=/integrations/hylafax/recvq
FAX_NOTIFY_XFERFAXLOG=/integrations/hylafax/log/xferfaxlog
FAX_NOTIFY_STATE_PATH=/data/faxmail/notified-recvq.json
FAX_NOTIFY_POLL_SECONDS=20
FAX_NOTIFY_MIN_FILE_AGE_SECONDS=60
FAX_NOTIFY_DELIVERY_FAILURE_ROOT=/integrations/hylafax/status/kaosgdd-faxmail/failed
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true
FAX_NOTIFY_TITLE=Incoming fax
FAX_NOTIFY_PRIORITY=high
FAX_NOTIFY_TAGS=fax,inbox
FAX_NOTIFY_CLICK_URL=https://roundcube.kaosgdd.net/
PUSHOVER_ENABLED=true
PUSHOVER_USER_KEY=
PUSHOVER_IOS_TOKEN=
PUSHOVER_IOS_DEVICE=iphone
PUSHOVER_DESKTOP_TOKEN=
PUSHOVER_DESKTOP_DEVICE=
```

Production mounts:

```text
/var/spool/hylafax:/integrations/hylafax:ro
/srv/kaos/data/kaosgdd/brain/faxmail:/data/faxmail
```

The first run marks existing `recvq/fax*.tif` files as already seen when:

```text
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=true
```

This avoids a notification storm after deployment. To force a test against
existing faxes, temporarily set:

```text
FAX_NOTIFY_MARK_EXISTING_ON_FIRST_RUN=false
```

Then delete:

```bash
sudo rm -f /srv/kaos/data/kaosgdd/brain/faxmail/notified-recvq.json
```

Check Brain status:

```bash
curl -s http://100.94.208.16:8092/api/brain/status | python3 -m json.tool
```

Look for:

```text
upstreams.faxmailNotifications.enabled = true
upstreams.faxmailNotifications.configured = true
upstreams.faxmailNotifications.lastError = ""
```

## End-To-End Migration Checklist

On a new system:

1. Clone `/srv/projects/KaosGDD`.
2. Install HylaFAX, Ghostscript, and libtiff tools.
3. Plug modem into direct USB 2.0.
4. Confirm `/dev/ttyACM0` and USB ID `0572:1340`.
5. Install the known-good ttyACM0 config.
6. Enable and start `hylafax.service` and `faxgetty@ttyACM0.service`.
7. Confirm `faxstat -s` reports scheduler running and modem idle.
8. Create `/etc/kaosgdd/faxmail.env`.
9. Confirm Cloudflare routes `fax-in@kaosgdd.net` to the destination mailbox.
10. Run `install-host-maintenance.sh --install` to install the mailbox hook,
    retry timer, local-only hfaxd binding, log rotation, backup timer, and
    30-day sent-fax retention timer.
11. Test an existing TIFF through `sudo -u uucp /bin/sh ... faxrcvd`.
12. Send one live fax and confirm PDF email arrives.
13. Enable Brain Pushover env.
14. Restart/deploy Brain.
15. Send one more live fax and confirm Pushover push.

## Backup List

Back these up before package upgrades, migration, or host rebuild:

```text
/etc/kaosgdd/faxmail.env
/var/spool/hylafax/etc/config.ttyACM0
/var/spool/hylafax/bin/faxrcvd
/var/spool/hylafax/recvq
/var/spool/hylafax/log/xferfaxlog
/var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log
/srv/kaos/data/kaosgdd/brain/faxmail/notified-recvq.json
```

Run the inventory helper:

```bash
sudo /srv/projects/KaosGDD/ops/faxmail/inventory-hylafax-host.sh /srv/kaos/data/kaosgdd/faxmail/inventory/hylafax-$(date +%Y%m%d-%H%M%S)
```

Do not commit inventory tarballs or env files.

Successfully emailed TIFFs are retained locally for 30 days. The retention
timer then deletes the `recvq` file and its local backup copy while preserving
the sent marker as an audit record. Failed or unconfirmed faxes are never
eligible for automatic deletion.

## Troubleshooting

Modem missing:

```text
faxgetty dependency failed
dev-ttyACM0.device is not active
ls: cannot access /dev/ttyACM0
```

Fix USB first. Use USB 2.0, direct port, then check `lsusb` and `dmesg`.

HylaFAX not reachable:

```text
Can not reach service hylafax at host "localhost".
```

Start:

```bash
sudo systemctl start hylafax.service
ss -tulpn | grep 4559 || true
faxstat -s
```

Live hook cannot run Python sender:

```text
/usr/bin/python3: can't open file ... Permission denied
```

Cause: `uucp` cannot traverse the repo. Re-run:

```bash
cd /srv/projects/KaosGDD
sudo ./ops/faxmail/install-mailbox-faxrcvd.sh --install
```

Live hook can log but cannot source env:

```text
skip: missing /etc/kaosgdd/faxmail.env
```

or silent SMTP failures only live, not manual. Check:

```bash
sudo -u uucp test -r /etc/kaosgdd/faxmail.env && echo env-ok
sudo ls -lah /etc/kaosgdd/faxmail.env
```

Email script says sent, but no mailbox message:

- Check Gmail All Mail and Spam.
- Confirm `FAXMAIL_TO=fax-in@kaosgdd.net`.
- Confirm Cloudflare route destination.
- Confirm `FAXMAIL_FROM` matches `FAXMAIL_SMTP_USER`.
- Avoid routing back into the same Gmail account used as SMTP sender.
- Send directly to the destination Gmail once to separate SMTP from Cloudflare.

Direct test:

```bash
sudo sh -c 'set -a; . /etc/kaosgdd/faxmail.env; set +a; FAXMAIL_TO=destination@gmail.com; /usr/bin/python3 /usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py /var/spool/hylafax/recvq/fax000000001.tif --remote-number direct-test --device ttyACM0 --commid 000000001 --force'
```

Brain Pushover does not notify:

- Confirm `FAX_NOTIFY_ENABLED=true`.
- Confirm Brain has `/var/spool/hylafax` mounted read-only at
  `/integrations/hylafax`.
- Confirm `/data/faxmail` is writable.
- Confirm the Pushover user key, application token, and explicit device name.
- Check `/api/brain/status`.
- If first-run marking is enabled, old faxes will not notify.

## Rollback

Restore the package `faxrcvd` and remove the diversion:

```bash
sudo ./ops/faxmail/restore-mailbox-faxrcvd.sh --restore-package
```

Restart receive service only if needed:

```bash
sudo systemctl restart faxgetty@ttyACM0.service
```

Disable Brain push without touching fax receive:

```text
FAX_NOTIFY_ENABLED=false
```

Then restart/deploy Brain.
