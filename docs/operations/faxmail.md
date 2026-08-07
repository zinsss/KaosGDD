# Faxmail Operations

Faxmail migration moves fax workflow to a hosted mailbox plus Brain worker while
preserving the working HylaFAX modem setup.

## Safety Rule

Do not move or reconfigure the modem until the current host is inventoried and
the mailbox path has been tested without touching HylaFAX hooks.

Also check the archived legacy repo before changing anything:

```text
/srv/projects/_archive/KaosGdd-web-archived-20260806-121403
```

The most useful legacy handoff document is:

```text
docs/fax-hylafax-operations.md
```

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

## Legacy Customization Checklist

Review these files before implementation or cutover:

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

Carry these lessons forward:

- **Client auth**: if `faxstat` prompts for `Password:` or reports `331
  Password required`, patch the active `hosts.hfaxd` with explicit `:::`
  no-password entries.
- **Path variance**: check all candidate auth/config paths:

  ```bash
  find /etc /var/spool -name hosts.hfaxd -print
  ```

- **Docker bridge**: old KaosGdd needed `host.docker.internal:host-gateway`
  and sometimes firewall allowance to host port `4559`. Brain may run on host
  instead, but any containerized worker must re-check this.
- **Outgoing conversion**: convert PDF to fax-ready TIFF before `sendfax`.
  Do not submit raw PDF to HylaFAX.
- **Known failure smell**: `/undefinedfilename` in `doneq` means HylaFAX tried
  to do PDF conversion in its spool context.
- **Status parsing**: `doneq/q*` files contain useful `jobid`, `number`,
  `status`, `statuscode`, `state`, and `returned` fields.
- **Lazy status was a compromise**: old KaosGdd synced `doneq` when opening
  fax list/detail. Brain should do this as worker behavior, not UI behavior.
- **Hook upgrades**: package updates may replace HylaFAX hooks. Always keep a
  timestamped backup before installing replacements.
- **Failure behavior**: missing `sendfax`, timed out `sendfax`, and provider
  failure should produce rejected/failed mailbox state and a notification, not
  a wedged worker.

The live `kaos` host currently uses `/var/spool/hylafax/etc/FaxDispatch` as the
incoming integration point. The archived repo also contains older wrapper
scripts for `/var/spool/hylafax/bin/faxrcvd`. Preserve the live path during the
first mailbox cutover unless inventory proves it has changed.

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

Keep inventory tarballs out of git.

## Incoming Fax To Mailbox

Test SMTP delivery before installing any hook:

```bash
TIFF=$(ls -1 /var/spool/hylafax/recvq/*.tif | tail -1)
sudo sh -c 'set -a; . /etc/kaosgdd/faxmail.env; set +a; /usr/bin/python3 /projects/KaosGDD/ops/faxmail/send-incoming-fax-email.py "$0" --remote-number test --device ttyACM0 --dry-run' "$TIFF"
```

Then send a real test email:

```bash
sudo sh -c 'set -a; . /etc/kaosgdd/faxmail.env; set +a; /usr/bin/python3 /projects/KaosGDD/ops/faxmail/send-incoming-fax-email.py "$0" --remote-number test --device ttyACM0' "$TIFF"
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
