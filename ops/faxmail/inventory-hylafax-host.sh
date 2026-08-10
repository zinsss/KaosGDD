#!/bin/sh
set -eu

umask 077

STAMP=$(date +%Y%m%d-%H%M%S)
OUT_DIR="${1:-/tmp/kaosgdd-faxmail-hylafax-inventory-$STAMP}"

mkdir -p \
  "$OUT_DIR/commands" \
  "$OUT_DIR/files" \
  "$OUT_DIR/systemd" \
  "$OUT_DIR/spool" \
  "$OUT_DIR/logs"

run_capture() {
  name="$1"
  shift
  {
    echo "$ $*"
    "$@" 2>&1 || true
  } > "$OUT_DIR/commands/$name.txt"
}

copy_if_exists() {
  path="$1"
  if [ -e "$path" ]; then
    mkdir -p "$OUT_DIR/files$(dirname "$path")"
    cp -a "$path" "$OUT_DIR/files$path" 2>/dev/null || true
  fi
}

copy_unit_if_exists() {
  unit="$1"
  for dir in /etc/systemd/system /lib/systemd/system /usr/lib/systemd/system; do
    if [ -e "$dir/$unit" ]; then
      mkdir -p "$OUT_DIR/systemd$dir"
      cp -a "$dir/$unit" "$OUT_DIR/systemd$dir/$unit" 2>/dev/null || true
    fi
  done
}

run_capture uname uname -a
run_capture os_release sh -c 'cat /etc/os-release'
run_capture date date -Is
run_capture systemctl_hylafax systemctl status hylafax.service faxq.service hfaxd.service faxgetty@ttyACM0.service
run_capture systemctl_hylafax_enabled sh -c 'for unit in hylafax.service faxq.service hfaxd.service faxgetty@ttyACM0.service; do printf "%s: " "$unit"; systemctl is-enabled "$unit" 2>&1 || true; done'
run_capture systemctl_fax_units sh -c 'systemctl list-unit-files "*fax*" "*hyla*" "*kaos*"'
run_capture faxstat_host faxstat -h localhost
run_capture faxstat_send faxstat -s
run_capture faxstat_done faxstat -d
run_capture hfaxd_listener sh -c 'ss -tulpn | grep -E ":4559|:444"'
run_capture usb_devices sh -c 'lsusb; echo; dmesg | grep -iE "ttyACM|ttyUSB|modem|fax" | tail -100'
run_capture hylafax_paths sh -c 'find /etc /var/spool -name hosts.hfaxd -o -name FaxDispatch -o -name "config*" 2>/dev/null | sort'
run_capture hylafax_bin_listing sh -c 'ls -lah /var/spool/hylafax/bin 2>/dev/null'
run_capture hylafax_queue_listing sh -c 'for d in recvq doneq sendq docq info etc; do echo "== $d =="; ls -lah "/var/spool/hylafax/$d" 2>/dev/null || true; done'
run_capture command_versions sh -c 'for c in faxstat sendfax faxq hfaxd faxgetty gs tiff2pdf; do printf "%s: " "$c"; command -v "$c" || true; done'
run_capture kaos_fax_files sh -c 'find /srv/kaos /srv/projects -maxdepth 6 \( -iname "*fax*" -o -iname "*hyla*" -o -iname "compose.y*ml" -o -iname "*.service" -o -iname "*.timer" \) 2>/dev/null | sort'
run_capture secret_file_metadata sh -c 'for path in /srv/kaos/secrets/kaosgdd-brain.env; do if [ -e "$path" ]; then stat -c "%A %U:%G %s %n" "$path"; sed -n "s/^\([A-Za-z_][A-Za-z0-9_]*\)=.*/\1=REDACTED/p" "$path"; fi; done'

for p in \
  /var/spool/hylafax/etc/config \
  /var/spool/hylafax/etc/config.ttyACM0 \
  /var/spool/hylafax/bin/faxrcvd \
  /etc/hylafax/hfaxd.systemd.conf
do
  copy_if_exists "$p"
done

for unit in \
  hylafax.service \
  faxq.service \
  hfaxd.service \
  faxgetty@ttyACM0.service \
  kaos-hylafax-backup.service \
  kaos-hylafax-backup.timer
do
  copy_unit_if_exists "$unit"
done

if [ -d /var/spool/hylafax ]; then
  find /var/spool/hylafax -maxdepth 3 -printf '%M %u %g %s %TY-%Tm-%Td %TH:%TM %p\n' \
    > "$OUT_DIR/spool/permissions.txt" 2>/dev/null || true
fi

ARCHIVE="$OUT_DIR.tar.gz"
tar -C "$(dirname "$OUT_DIR")" -czf "$ARCHIVE" "$(basename "$OUT_DIR")"
chmod 0600 "$ARCHIVE"

echo "Inventory written to:"
echo "$OUT_DIR"
echo "$ARCHIVE"
