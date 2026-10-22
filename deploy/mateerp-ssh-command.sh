#!/usr/bin/env bash
# Dedicated SSH forced command, no shell, no port forwarding.
set -euo pipefail
[[ "${SSH_ORIGINAL_COMMAND:-}" =~ ^deploy[[:space:]]sha-[a-f0-9]{40}[[:space:]][a-zA-Z0-9-]{1,39}$ ]] || {
  echo 'Unsupported deployment request' >&2
  exit 20
}
{ printf '%s\n' "$SSH_ORIGINAL_COMMAND"; cat; } | sudo -n /usr/local/sbin/mateerp-deploy
