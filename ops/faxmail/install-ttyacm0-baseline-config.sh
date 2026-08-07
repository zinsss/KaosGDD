#!/bin/sh
set -eu

CONFIG_PATH="${CONFIG_PATH:-/var/spool/hylafax/etc/config.ttyACM0}"
TEMPLATE_PATH="${TEMPLATE_PATH:-/srv/projects/KaosGDD/ops/faxmail/templates/config.ttyACM0.kaosgdd-baseline}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "Missing template: $TEMPLATE_PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$CONFIG_PATH")"

if [ -f "$CONFIG_PATH" ]; then
  cp -a "$CONFIG_PATH" "$CONFIG_PATH.pre-kaosgdd-baseline.$STAMP"
fi

install -o uucp -g uucp -m 0644 "$TEMPLATE_PATH" "$CONFIG_PATH"

echo "Installed KaosGDD ttyACM0 HylaFAX baseline config:"
echo "  $CONFIG_PATH"
echo
echo "Backups:"
ls -lah "$CONFIG_PATH".pre-kaosgdd-baseline.* 2>/dev/null || true
echo
echo "Effective settings:"
grep -E '^(CountryCode|AreaCode|FAXNumber|RingsBeforeAnswer|MaxRecvPages|ModemType|ModemRate|ModemFlowControl|Class1ECMSupport|Class1PersistentECM|Class1ECMFrameSize):' "$CONFIG_PATH"
