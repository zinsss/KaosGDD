#!/bin/sh
set -eu

MODE="${1:-}"
FAXRCVD_PATH="${FAXRCVD_PATH:-/var/spool/hylafax/bin/faxrcvd}"
TEMPLATE_PATH="${TEMPLATE_PATH:-/srv/projects/KaosGDD/ops/faxmail/templates/faxrcvd.telegram}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" != "--install" ]; then
  echo "Usage: sudo $0 --install" >&2
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

if command -v dpkg-divert >/dev/null 2>&1; then
  if ! dpkg-divert --list "$FAXRCVD_PATH" | grep -Fq "$FAXRCVD_PATH"; then
    dpkg-divert --quiet --local --add --no-rename \
      --divert "$FAXRCVD_PATH.distrib" "$FAXRCVD_PATH"
  fi
fi

if [ -f "$FAXRCVD_PATH" ]; then
  cp -a "$FAXRCVD_PATH" "$FAXRCVD_PATH.pre-kaosgdd-telegram.$STAMP"
fi
install -o uucp -g uucp -m 0755 "$TEMPLATE_PATH" "$FAXRCVD_PATH"

echo "Installed Telegram-only faxrcvd hook: $FAXRCVD_PATH"
