#!/bin/sh
set -u

DEVICE="${1:-ttyACM0}"
CONFIG_PATH="${CONFIG_PATH:-/var/spool/hylafax/etc/config.$DEVICE}"
ROOT="${ROOT:-/srv/projects/KaosGDD}"
FAILED=0

check() {
  label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'ok   %s\n' "$label"
  else
    printf 'FAIL %s\n' "$label"
    FAILED=1
  fi
}

echo "== Device and configuration =="
check "/dev/$DEVICE exists" test -c "/dev/$DEVICE"
check "$CONFIG_PATH exists" test -f "$CONFIG_PATH"
if [ -f "$CONFIG_PATH" ]; then
  grep -E '^(CountryCode|AreaCode|RingsBeforeAnswer|MaxRecvPages|ModemType|ModemRate|ModemFlowControl|Class1ECMSupport|Class1PersistentECM|Class1ECMFrameSize):' "$CONFIG_PATH" || true
fi
echo

echo "== Services =="
for unit in hylafax.service faxq.service hfaxd.service "faxgetty@$DEVICE.service"; do
  check "$unit active" systemctl is-active --quiet "$unit"
done
check "hylafax.service enabled at boot" systemctl is-enabled --quiet hylafax.service
check "faxgetty@$DEVICE.service enabled at boot" systemctl is-enabled --quiet "faxgetty@$DEVICE.service"
check "mail retry timer enabled" systemctl is-enabled --quiet kaos-faxmail-retry.timer
check "recvq backup timer enabled" systemctl is-enabled --quiet kaos-hylafax-backup.timer
check "fax retention timer enabled" systemctl is-enabled --quiet kaos-faxmail-retention.timer
echo

echo "== Outbound queue runtime =="
FAXQ_PID=$(systemctl show faxq.service --property MainPID --value 2>/dev/null || true)
if [ -n "$FAXQ_PID" ] && [ "$FAXQ_PID" -gt 0 ] 2>/dev/null; then
  check "faxq runtime sees generated setup.cache" \
    nsenter -t "$FAXQ_PID" -m -- test -r /var/spool/hylafax/etc/setup.cache
  check "faxq runtime sees modem configuration" \
    nsenter -t "$FAXQ_PID" -m -- test -r "/var/spool/hylafax/etc/config.$DEVICE"
else
  echo "FAIL faxq has no running process"
  FAILED=1
fi
echo

echo "== Local protocol exposure =="
check "hfaxd listens on localhost:4559" sh -c "ss -ltn | grep -qE '127\\.0\\.0\\.1:4559'"
check "hfaxd access rules match maintained template" cmp -s \
  /etc/hylafax/hosts.hfaxd "$ROOT/ops/faxmail/templates/hosts.hfaxd.kaosgdd"
if ss -ltn | grep -qE '(^|[[:space:]])[^[:space:]]*:444[[:space:]]'; then
  echo "FAIL unused SNPP port 444 is listening"
  FAILED=1
else
  echo "ok   unused SNPP port 444 is closed"
fi
echo

echo "== Mailbox hook =="
check "faxrcvd matches maintained template" cmp -s \
  /var/spool/hylafax/bin/faxrcvd "$ROOT/ops/faxmail/templates/faxrcvd.mailbox"
check "installed sender matches maintained source" cmp -s \
  /usr/local/lib/kaosgdd/faxmail/send-incoming-fax-email.py \
  "$ROOT/ops/faxmail/send-incoming-fax-email.py"
check "faxrcvd package diversion installed" sh -c \
  "dpkg-divert --list /var/spool/hylafax/bin/faxrcvd | grep -q /var/spool/hylafax/bin/faxrcvd"

FAILURE_ROOT=/var/spool/hylafax/status/kaosgdd-faxmail/failed
FAILURE_COUNT=$(find "$FAILURE_ROOT" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)
if [ "$FAILURE_COUNT" -eq 0 ]; then
  echo "ok   no pending mailbox delivery failures"
else
  echo "FAIL pending mailbox delivery failures: $FAILURE_COUNT"
  FAILED=1
fi
echo

echo "== HylaFAX status =="
faxstat -s 2>&1 || FAILED=1
faxstat -r 2>&1 || FAILED=1

exit "$FAILED"
