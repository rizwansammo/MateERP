#!/usr/bin/env bash
# Run after approved main-branch deployment; affects MateERP only.
set -Eeuo pipefail
if (( EUID != 0 )); then
  echo 'This installer needs root; run sudo bash deploy/aia/install.sh' >&2
  exit 1
fi
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test -f /opt/MateERP/.env.production
test -s /opt/MateERP/compose.production.yml
test -s "$source_dir/rotate.py"
test -s "$source_dir/mateerp-aia-rotation.service"
test -s "$source_dir/mateerp-aia-rotation.timer"
install -d -o root -g root -m 0700 /etc/mateerp/aia
install -d -o root -g root -m 0700 /usr/local/libexec/mateerp-aia
install -o root -g root -m 0700 "$source_dir/rotate.py" /usr/local/libexec/mateerp-aia/rotate.py
install -o root -g root -m 0644 "$source_dir/mateerp-aia-rotation.service" /etc/systemd/system/mateerp-aia-rotation.service
install -o root -g root -m 0644 "$source_dir/mateerp-aia-rotation.timer" /etc/systemd/system/mateerp-aia-rotation.timer
/usr/bin/python3 -m py_compile /usr/local/libexec/mateerp-aia/rotate.py
systemctl daemon-reload
systemctl enable --now mateerp-aia-rotation.timer
systemctl start mateerp-aia-rotation.service
echo 'MateERP AIA daily rotation timer installed and first credential verified.'
