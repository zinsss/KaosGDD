#!/bin/sh
set -eu

MODE="${1:-}"
FAXDISPATCH_PATH="${FAXDISPATCH_PATH:-/var/spool/hylafax/etc/FaxDispatch}"
TEMPLATE_PATH="${TEMPLATE_PATH:-/srv/projects/KaosGDD/ops/faxmail/templates/FaxDispatch.mailbox}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" != "--install" ]; then
  cat <<EOF
Usage:
  sudo $0 --install

This backs up the current FaxDispatch and installs:
  $TEMPLATE_PATH

Target:
  $FAXDISPATCH_PATH

Dry-run checks:
EOF
  if [ -f "$FAXDISPATCH_PATH" ]; then
    echo "  current exists: $FAXDISPATCH_PATH"
  else
    echo "  current missing: $FAXDISPATCH_PATH"
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

if [ -f "$FAXDISPATCH_PATH" ]; then
  cp -a "$FAXDISPATCH_PATH" "$FAXDISPATCH_PATH.pre-kaosgdd-faxmail-mailbox.$STAMP"
fi

install -o uucp -g uucp -m 0755 "$TEMPLATE_PATH" "$FAXDISPATCH_PATH"

echo "Installed mailbox FaxDispatch:"
ls -lah "$FAXDISPATCH_PATH"
echo
echo "Backups:"
ls -lah "$FAXDISPATCH_PATH".pre-kaosgdd-faxmail-mailbox.* 2>/dev/null || true
