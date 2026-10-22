# Automatic AIA API credential renewal

The `assistant` / `assistant@netamate.com` account is permanent. Its
API **credential**, not its user account, is valid for **90 days**.

## How it works

- The **MateServer** systemd timer checks **daily** (on boot and around 04:15
  server local time). Only after the current token's file is 60 days old does
  it renew; first run creates the initial token automatically.
- The root-only Python script calls the existing Django
  `issue_aia_token --days 90` command without printing the returned
  credential, then proves it works against the HTTPS API: allowed Customer
  GET is 200 and forbidden Users GET is 403.
- The script writes the new token to a root-only temporary file, `fsync`s
  it, atomically replaces `/etc/mateerp/aia/token`, and revokes the previous
  token by non-secret prefix.
- A private `token.previous` backup supports recovery if the host crashes
  between the atomic file swap and revocation. The next run handles it.
- During an unsuccessful issuance or HTTPS test, the existing token remains
  active and the newly issued candidate is revoked if possible. The timer
  retries automatically on its next scheduled run.
- The token and files are never stored in GitHub, code, logs, ChatGPT, API
  responses or process arguments. Only a user-approved authorized VPS
  connection can use it locally.
- ChatGPT **does not have independent, always-on server access**. This
  enables reliable credentials *when* an authorized ChatGPT/server
  connection performs an operation; the timer does not initiate AI actions.

## Initial installation (once, after CI and production deployment)

Use the matching reviewed `main` checkout from GitHub. Then, as root:

```bash
cd /path/to/verified/MateERP
sudo bash deploy/aia/install.sh
```

The installer creates a dedicated service and timer. It triggers the first
bootstrap immediately; no password and no private API key needs copying.
Do not paste credential content anywhere.

## Status (never print the credential)

```bash
systemctl status mateerp-aia-rotation.timer --no-pager
systemctl status mateerp-aia-rotation.service --no-pager
systemctl list-timers mateerp-aia-rotation.timer
sudo stat -c '%n %a %U' /etc/mateerp/aia/token
```

The token file should be root-owned and mode `600`. The directory should
be root-owned and mode `700`.

## Emergency stop, incident, or account deactivation

```bash
sudo systemctl disable --now mateerp-aia-rotation.timer
```

Then revoke the current token in Django (by its **public prefix**, not the
secret), or deactivate the `assistant` user. Stopping the timer alone
stops renewal, **not** existing token access. When rotating on demand,
`sudo systemctl start mateerp-aia-rotation.service` checks the current
token's age and renews only when due. Never `cat` the token into a chat.

## Boundaries

AIA tokens only authorize the explicit endpoint/method/scope allowlist and
the account's assigned permissions. They cannot issue invoices, approve
payments, perform financial posting, manage users or change founders' records.
**Tokens must be reloaded from the server file for new requests.** An
in-flight request racing exactly with rotation may have to retry after
reloading; no ongoing browser session is supported by this account.

No offsite token storage is configured. If the OS is lost, the operator must
restore access and credential storage securely. A failed daily timer run
is visible in `systemctl --failed` and the system journal. For proactive
alerts, attach the team's monitoring system to service failures.
