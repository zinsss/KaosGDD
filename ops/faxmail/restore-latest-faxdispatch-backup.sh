#!/bin/sh
set -eu

FAXDISPATCH_PATH="${FAXDISPATCH_PATH:-/var/spool/hylafax/etc/FaxDispatch}"
BACKUP=$(ls -1 "$FAXDISPATCH_PATH".pre-kaosgdd-faxmail-mailbox.* 2>/dev/null | sort | tail -1)

if [ -z "$BACKUP" ]; then
  echo "No KaosGDD faxmail FaxDispatch backup found." >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

cp -a "$BACKUP" "$FAXDISPATCH_PATH"

echo "Restored:"
echo "$BACKUP -> $FAXDISPATCH_PATH"
ls -lah "$FAXDISPATCH_PATH"
