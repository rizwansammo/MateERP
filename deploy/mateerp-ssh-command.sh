#!/usr/bin/env bash
# Dedicated SSH forced command, no shell, no port forwarding.
set -euo pipefail
[[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy[[:space:]]sha-[a-f0-9]{40}$ ]] || {
  echo 'Unsupported deployment request' >&2
  exit 20
}
printf '%s\n' "$SSH_ORIGINAL_COMMAND" | sudo -n /usr/local/sbin/mateerp-deploy
