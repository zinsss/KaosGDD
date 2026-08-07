#!/bin/sh
set -u

DEVICE="${1:-ttyACM0}"
CONFIG_PATH="${CONFIG_PATH:-/var/spool/hylafax/etc/config.$DEVICE}"

echo "== Device =="
ls -lah "/dev/$DEVICE" 2>&1 || true
echo

echo "== USB modem hints =="
lsusb 2>/dev/null | grep -Ei 'conexant|rockwell|modem|fax|0572:1340' || true
echo

echo "== HylaFAX commands =="
for cmd in faxstat sendfax faxq hfaxd faxgetty gs tiff2pdf; do
  printf '%-10s ' "$cmd:"
  command -v "$cmd" || true
done
echo

echo "== Spool paths =="
for path in \
  /var/spool/hylafax \
  /var/spool/hylafax/etc \
  /var/spool/hylafax/recvq \
  /var/spool/hylafax/sendq \
  /var/spool/hylafax/doneq \
  /var/spool/hylafax/log
do
  ls -ld "$path" 2>&1 || true
done
echo

echo "== Modem config =="
if [ -f "$CONFIG_PATH" ]; then
  ls -lah "$CONFIG_PATH"
  grep -E '^(CountryCode|AreaCode|RingsBeforeAnswer|MaxRecvPages|ModemType|ModemRate|ModemFlowControl|Class1ECMSupport|Class1PersistentECM|Class1ECMFrameSize):' "$CONFIG_PATH" || true
else
  echo "missing: $CONFIG_PATH"
fi
echo

echo "== Services =="
systemctl status "faxgetty@$DEVICE.service" hylafax-core.service kaos-hylafax-daemons.service --no-pager 2>&1 || true
echo

echo "== HylaFAX queues =="
faxstat -s 2>&1 || true
faxstat -d 2>&1 || true
