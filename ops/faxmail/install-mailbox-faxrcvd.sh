#!/bin/sh
set -eu

MODE="${1:-}"
FAXRCVD_PATH="${FAXRCVD_PATH:-/var/spool/hylafax/bin/faxrcvd}"
TEMPLATE_PATH="${TEMPLATE_PATH:-/srv/projects/KaosGDD/ops/faxmail/templates/faxrcvd.mailbox}"
LOG_PATH="${LOG_PATH:-/var/spool/hylafax/log/kaosgdd-faxmail-faxdispatch.log}"
ENV_FILE="${ENV_FILE:-/etc/kaosgdd/faxmail.env}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" != "--install" ]; then
  cat <<EOF
Usage:
  sudo $0 --install

This backs up the current faxrcvd and installs:
  $TEMPLATE_PATH

Target:
  $FAXRCVD_PATH

Dry-run checks:
EOF
  if [ -f "$FAXRCVD_PATH" ]; then
    echo "  current exists: $FAXRCVD_PATH"
  else
    echo "  current missing: $FAXRCVD_PATH"
  fi
  if [ -f "$TEMPLATE_PATH" ]; then
    echo "  template exists: $TEMPLATE_PATH"
  else
    echo "  template missing: $TEMPLATE_PATH"
  fi
  exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "Missing template: $TEMPLATE_PATH" >&2
  exit 1
fi

if [ -f "$FAXRCVD_PATH" ]; then
  cp -a "$FAXRCVD_PATH" "$FAXRCVD_PATH.pre-kaosgdd-faxmail-mailbox.$STAMP"
fi

install -o uucp -g uucp -m 0755 "$TEMPLATE_PATH" "$FAXRCVD_PATH"

mkdir -p "$(dirname "$LOG_PATH")"
touch "$LOG_PATH"
chown uucp:uucp "$LOG_PATH"
chmod 0640 "$LOG_PATH"

if [ -f "$ENV_FILE" ]; then
  chgrp uucp "$ENV_FILE"
  chmod 0640 "$ENV_FILE"
fi

echo "Installed mailbox faxrcvd:"
ls -lah "$FAXRCVD_PATH"
echo
echo "Prepared live hook access:"
ls -lah "$LOG_PATH"
if [ -f "$ENV_FILE" ]; then
  ls -lah "$ENV_FILE"
else
  echo "missing env file: $ENV_FILE"
fi
echo
echo "Backups:"
ls -lah "$FAXRCVD_PATH".pre-kaosgdd-faxmail-mailbox.* 2>/dev/null || true
