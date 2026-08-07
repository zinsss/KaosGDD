# Faxmail Operations

Faxmail migration moves fax workflow to a hosted mailbox plus Brain worker while
preserving the working HylaFAX modem setup.

## Safety Rule

Do not move or reconfigure the modem until the current host is inventoried and
the mailbox path has been tested without touching HylaFAX hooks.

## Current Host

Current modem host:

```text
kaos
```

Known working pieces:

```text
faxgetty@ttyACM0.service
kaos-hylafax-daemons.service
/var/spool/hylafax/etc/FaxDispatch
/var/spool/hylafax/etc/config.ttyACM0
/etc/udev/rules.d/99-faxmodem.rules
```

The custom daemon unit starts:

```text
/usr/sbin/faxq
/usr/sbin/hfaxd -i hylafax
```

`hylafax-core.service` is not the active service model on this host.

## Hosted Mailbox

Create hosted mailboxes or aliases:

```text
fax@kaosgdd.net
fax-send@kaosgdd.net
```

Optional aliases:

```text
fax-in@kaosgdd.net      -> fax@kaosgdd.net
fax-failed@kaosgdd.net  -> fax@kaosgdd.net
```

Suggested folders:

```text
Incoming
OutgoingRequests
Processed
Rejected
Failed
Archive
```

## Inventory

Run before changing HylaFAX configs, hooks, services, or modem placement:

```bash
sudo /projects/KaosGDD/ops/faxmail/inventory-hylafax-host.sh /docker/kaosgdd/faxmail/inventory/hylafax-before-mailbox-cutover
```

If the helper script has not yet been moved into KaosGDD, use the temporary
copy from the archived KaosFaxMail planning repo before deleting the clone:

```bash
sudo /projects/KaosFaxMail/ops/host/inventory-hylafax-host.sh /docker/kaosgdd/faxmail/inventory/hylafax-before-mailbox-cutover
```

Keep inventory tarballs out of git.

## Incoming Fax To Mailbox

Test SMTP delivery before installing any hook:

```bash
TIFF=$(ls -1 /var/spool/hylafax/recvq/*.tif | tail -1)
sudo sh -c 'set -a; . /etc/kaosfaxmail/faxmail.env; set +a; /usr/bin/python3 /projects/KaosGDD/ops/faxmail/send-incoming-fax-email.py "$0" --remote-number test --device ttyACM0 --dry-run' "$TIFF"
```

Then send a real test email:

```bash
sudo sh -c 'set -a; . /etc/kaosfaxmail/faxmail.env; set +a; /usr/bin/python3 /projects/KaosGDD/ops/faxmail/send-incoming-fax-email.py "$0" --remote-number test --device ttyACM0' "$TIFF"
```

Only after Roundcube receives the PDF should `FaxDispatch` be changed.

## Outgoing Fax Worker

Brain should accept only messages matching:

```text
To: fax-send@kaosgdd.net
Subject: fax:0548209762
Attachment: exactly one PDF
```

Reject before calling HylaFAX when:

- sender is unauthorized
- subject has no parseable fax number
- no PDF is attached
- more than one PDF is attached
- attachment is not a valid PDF

Rejected messages should move to `Rejected` and get a short reason. Silent
ignore is allowed only for clearly unauthorized/spam messages.

## Cutover Test

1. Inventory host.
2. Confirm hosted mailbox and Roundcube access.
3. Confirm SMTP submission from host to mailbox.
4. Send one test incoming fax and confirm PDF arrival.
5. Send one authorized outgoing PDF request.
6. Confirm Brain submits TIFF to HylaFAX.
7. Confirm `faxstat -s` and `faxstat -d`.
8. Confirm folder move and notification.

## Rollback

Before changing `FaxDispatch`, back up:

```text
/var/spool/hylafax/etc/FaxDispatch
/var/spool/hylafax/bin/faxrcvd
/var/spool/hylafax/etc/config
/var/spool/hylafax/etc/config.ttyACM0
/etc/systemd/system/kaos-hylafax-daemons.service
```

Rollback should restore the previous `FaxDispatch`. Restart services only if
HylaFAX behaves unexpectedly:

```bash
sudo systemctl restart kaos-hylafax-daemons.service
sudo systemctl restart faxgetty@ttyACM0.service
```
