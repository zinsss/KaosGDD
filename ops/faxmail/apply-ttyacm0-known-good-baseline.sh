#!/bin/sh
set -eu

CONFIG_PATH="${CONFIG_PATH:-/var/spool/hylafax/etc/config.ttyACM0}"
STAMP=$(date +%Y%m%d-%H%M%S)

if [ "$(id -u)" -ne 0 ]; then
  echo "Run with sudo." >&2
  exit 1
fi

if [ ! -f "$CONFIG_PATH" ]; then
  cat >&2 <<EOF
Missing modem config:
  $CONFIG_PATH

If faxaddmodem probing hangs or does not create this file, use:

  sudo /srv/projects/KaosGDD/ops/faxmail/install-ttyacm0-baseline-config.sh

This script only applies the KaosGDD known-good overrides to an existing modem
config.
EOF
  exit 1
fi

backup="$CONFIG_PATH.pre-kaosgdd-known-good.$STAMP"
cp -a "$CONFIG_PATH" "$backup"

tmp=$(mktemp)
cleanup() {
  rm -f "$tmp"
}
trap cleanup EXIT

awk '
  BEGIN {
    skip["CountryCode"] = 1
    skip["AreaCode"] = 1
    skip["RingsBeforeAnswer"] = 1
    skip["MaxRecvPages"] = 1
    skip["ModemType"] = 1
    skip["ModemRate"] = 1
    skip["ModemFlowControl"] = 1
    skip["Class1ECMSupport"] = 1
    skip["Class1PersistentECM"] = 1
    skip["Class1ECMFrameSize"] = 1
  }
  {
    key = $1
    sub(/:$/, "", key)
    if (key in skip) {
      next
    }
    print
  }
' "$CONFIG_PATH" > "$tmp"

cat >> "$tmp" <<'EOF'

# KaosGDD known-good ttyACM0 baseline.
# Captured from the working Conexant/Rockwell USB modem host before migration.
CountryCode:            82
AreaCode:               054
RingsBeforeAnswer:      1
MaxRecvPages:           25
ModemType:              Class1
ModemRate:              38400
ModemFlowControl:       rtscts
Class1ECMSupport:       No
Class1PersistentECM:    No
Class1ECMFrameSize:     64
EOF

install -o uucp -g uucp -m 0644 "$tmp" "$CONFIG_PATH"

echo "Applied KaosGDD known-good modem baseline:"
echo "  $CONFIG_PATH"
echo
echo "Backup:"
echo "  $backup"
echo
echo "Effective settings:"
grep -E '^(CountryCode|AreaCode|RingsBeforeAnswer|MaxRecvPages|ModemType|ModemRate|ModemFlowControl|Class1ECMSupport|Class1PersistentECM|Class1ECMFrameSize):' "$CONFIG_PATH"
