#!/bin/sh
set -eu

MODE="${1:-}"
ROOT="${ROOT:-/srv/projects/KaosGDD}"
FAXMAIL="$ROOT/ops/faxmail"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" != "--install" ]; then
  echo "Usage: sudo $0 --install" >&2
  exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

for command in dpkg-divert logrotate rsync sha256sum systemctl; do
  if ! command -v "$command" >/dev/null 2>&1; then
    echo "Missing required command: $command" >&2
    exit 1
  fi
done

install -d -o root -g root -m 0700 /srv/kaos/backups/hylafax/host-maintenance
install -d -o root -g root -m 0700 /srv/kaos/backups/faxmail
cp -a /etc/hylafax/hfaxd.systemd.conf \
  "/srv/kaos/backups/hylafax/host-maintenance/hfaxd.systemd.conf.$STAMP"

"$FAXMAIL/install-mailbox-faxrcvd.sh" --install
install -o root -g root -m 0755 \
  "$FAXMAIL/backup-hylafax-recvq.sh" /usr/local/sbin/kaos-hylafax-backup
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/hfaxd.systemd.conf.kaosgdd" /etc/hylafax/hfaxd.systemd.conf
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/kaos-faxmail-retry.service" /etc/systemd/system/kaos-faxmail-retry.service
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/kaos-faxmail-retry.timer" /etc/systemd/system/kaos-faxmail-retry.timer
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/kaos-hylafax-backup.service" /etc/systemd/system/kaos-hylafax-backup.service
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/kaos-hylafax-backup.timer" /etc/systemd/system/kaos-hylafax-backup.timer
install -o root -g root -m 0644 \
  "$FAXMAIL/templates/kaosgdd-faxmail.logrotate" /etc/logrotate.d/kaosgdd-faxmail

systemctl daemon-reload
systemctl enable hylafax.service
systemctl enable --now kaos-faxmail-retry.timer kaos-hylafax-backup.timer
systemctl restart hfaxd.service

systemctl start kaos-hylafax-backup.service

"$FAXMAIL/verify-hylafax-modem-ready.sh" ttyACM0
