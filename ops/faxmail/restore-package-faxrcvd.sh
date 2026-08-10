#!/bin/sh
set -eu

MODE="${1:-}"
FAXRCVD_PATH="${FAXRCVD_PATH:-/var/spool/hylafax/bin/faxrcvd}"
ORIGINAL_PATH="${ORIGINAL_PATH:-$FAXRCVD_PATH.package-original}"
DISTRIBUTION_PATH="${DISTRIBUTION_PATH:-$FAXRCVD_PATH.distrib}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$MODE" != "--restore-package" ]; then
  echo "Usage: sudo $0 --restore-package" >&2
  exit 2
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

SOURCE=""
if [ -f "$DISTRIBUTION_PATH" ]; then
  SOURCE="$DISTRIBUTION_PATH"
elif [ -f "$ORIGINAL_PATH" ]; then
  SOURCE="$ORIGINAL_PATH"
fi

if [ -z "$SOURCE" ]; then
  echo "No package faxrcvd copy is available to restore." >&2
  exit 1
fi

cp -a "$FAXRCVD_PATH" "$FAXRCVD_PATH.pre-package-restore.$STAMP"
install -o uucp -g uucp -m 0755 "$SOURCE" "$FAXRCVD_PATH"

if command -v dpkg-divert >/dev/null 2>&1 && \
   dpkg-divert --list "$FAXRCVD_PATH" | grep -Fq "$FAXRCVD_PATH"; then
  dpkg-divert --quiet --local --remove --no-rename "$FAXRCVD_PATH"
fi

echo "Restored package faxrcvd from $SOURCE"
