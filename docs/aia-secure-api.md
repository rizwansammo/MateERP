# AIA (AI Assistant) — Secure API Integration

This integration uses the dedicated MateERP identity `assistant` / `assistant@netamate.com`
and the existing `AI Assistant Integration` role. The identity **must** have an
unusable password, not be a Django staff/admin, and remain enabled. Never give
a human administrator's password to an automation.

## Security design

- Bearer tokens have 36 random bytes of entropy; the database holds only a SHA-256
  digest and a short public prefix, never the plaintext token.
- Each token has a 1–90-day expiry, independent scope list, optional immediate
  revocation, last-used timestamp, and issuance/revocation audit entries.
- Tokens must match this dedicated username, email, active integration role,
  and an unusable password. Removing the role or deactivating the user blocks them.
- A successful bearer request must satisfy *both* the account permissions and
  the scope **and** the exact allowlisted path + HTTP method. Other endpoints fail
  closed. No token can access roles, users, founder finance, admin settings,
  payments, posting endpoints, invoice issuance, file uploads or document downloads.
- Existing Django session login + CSRF authentication remains untouched. Bearer
  credentials are never accepted over HTTP in production.
- Transactions and edits remain governed by existing domain validation and
  business rules. This layer adds restrictions; it never bypasses them.
- Tokens are not shown in logs, API responses, exception messages, or audit records.
- All actions executed by a token run as `assistant`, preserving normal audit actor.
  The human instruction and justification should be noted in the record itself.

## Allowed HTTP operations

| Endpoint pattern | GET | POST | PATCH/PUT |
| --- | --- | --- | --- |
| `/api/v1/sales/customers/` and `/<id>/` | customers.read | customers.write | customers.write |
| `/api/v1/purchasing/vendors/` and `/<id>/` | vendors.read | vendors.write | vendors.write |
| `/api/v1/billing/invoices/` and `/<id>/` | invoices.read | invoices.draft | invoices.draft |
| `/api/v1/documents/` and `/<id>/` | documents.read | denied | denied |
| `/api/v1/reporting/dashboard/` and `/search/` | reporting.read | denied | denied |
| `/api/v1/company/summary/` | company.read | denied | denied |

Note: Invoice editing uses the existing service's draft-only checks and requires
`invoices.create`. Issuing an invoice is a different endpoint and is DENIED.
Expense/vendor bill permissions can cause financial posting, so those are
deliberately **not included** in the initial integration role or token policy.

## Safe first-time credential provisioning (server operator)

Only after the feature is merged and production deployment has passed:

```bash
sudo install -d -o root -g root -m 700 /etc/mateerp/aia
sudo bash -c 'set -euo pipefail; umask 077; cd /opt/MateERP; docker compose -p mateerp --env-file .env.production -f compose.production.yml exec -T backend python manage.py issue_aia_token --name "MateERP AIA" --days 30 > /etc/mateerp/aia/token; chmod 600 /etc/mateerp/aia/token'
```

Do **not** paste the token into a conversation, an issue, a GitHub secret, a
command line argument, or application code. If remote automation needs the token,
perform API calls *on MateServer* from the authorized connection, reading this
root-owned token file. Do not echo tokens to tool output.

Example authenticated READ request using the HTTPS application proxy:

```bash
sudo bash -c 'token="$(cat /etc/mateerp/aia/token)"; curl -fsS --proto "=https" --tlsv1.2 -H "Authorization: Bearer $token" -H "Accept: application/json" "https://erp.netamate.com/api/v1/sales/customers/?page=1"'
```

For any production data write, first validate the request and data with the
business owner, show a preview of the intended operation when practical,
write only what was authorized, then verify by reading the resulting record.

## Revocation and rotation

Never output raw tokens when checking status. To revoke by non-secret prefix,
use `python manage.py revoke_aia_token <prefix>` in the running backend.
If compromised, revoke immediately. To rotate, issue the replacement to a new
0600 file, verify it, then revoke the previous prefix and atomically move the
new credential to `/etc/mateerp/aia/token`.

Deleting `/etc/mateerp/aia/token` stops this server-side integration workflow
from using it, but *does not revoke* the token already issued; revoke in Django.
AIA access is disabled immediately by deactivating the account or changing its
role. No long-lived token is committed to GitHub.

For a later enterprise UI, consider exposing administrator-only
issue/revoke/list actions with full audit history and one-time secret display.
