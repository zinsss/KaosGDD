#!/bin/sh
set -eu

umask 077

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

SPOOL_ROOT="${HYLAFAX_SPOOL_ROOT:-/var/spool/hylafax}"
BACKUP_ROOT="${HYLAFAX_BACKUP_ROOT:-/srv/kaos/backups/faxmail}"
CURRENT="$BACKUP_ROOT/current"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ ! -d "$SPOOL_ROOT/recvq" ]; then
  echo "Missing HylaFAX receive queue: $SPOOL_ROOT/recvq" >&2
  exit 1
fi

install -d -o root -g root -m 0700 \
  "$BACKUP_ROOT" "$BACKUP_ROOT/recvq" "$CURRENT"

rsync -a --ignore-existing --chmod=D700,F600 \
  "$SPOOL_ROOT/recvq/" "$BACKUP_ROOT/recvq/"

for source in \
  /etc/hylafax/config \
  /etc/hylafax/config.ttyACM0 \
  /etc/hylafax/hfaxd.systemd.conf \
  "$SPOOL_ROOT/log/xferfaxlog" \
  "$SPOOL_ROOT/bin/faxrcvd"
do
  if [ -f "$source" ]; then
    name=$(printf '%s' "$source" | sed 's#^/##; s#/#__#g')
    install -o root -g root -m 0600 "$source" "$CURRENT/$name"
  fi
done

manifest_tmp="$BACKUP_ROOT/.recvq-sha256.$STAMP.tmp"
find "$BACKUP_ROOT/recvq" -maxdepth 1 -type f -name 'fax*.tif' -print0 \
  | sort -z \
  | xargs -0 -r sha256sum > "$manifest_tmp"
mv "$manifest_tmp" "$BACKUP_ROOT/recvq-sha256.txt"
chmod 0600 "$BACKUP_ROOT/recvq-sha256.txt"

printf 'backupAt=%s\nsource=%s\nfiles=%s\n' \
  "$(date -Is)" \
  "$SPOOL_ROOT/recvq" \
  "$(find "$BACKUP_ROOT/recvq" -maxdepth 1 -type f -name 'fax*.tif' | wc -l)" \
  > "$CURRENT/status.txt"
chmod 0600 "$CURRENT/status.txt"

echo "HylaFAX recvq backup complete: $BACKUP_ROOT"
