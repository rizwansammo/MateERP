# MateERP Phase 7E — CI/CD, GHCR and Staging Acceptance

**Date:** 2026-10-22 (Asia/Dhaka). **Deployment state:** Phase 7E staging only; `erp.netamate.com` production not changed.

## Verified live CI and GHCR

- First integrated release commit: `a7d8780ca1d7425a29d3a06903492dbe4e8917e5`. GitHub Actions run `39756901728`: frontend and backend CI passed; GHCR frontend and backend build/publish succeeded; production deploy correctly skipped.
- Subsequent staged pipeline commit: `806e5f80979417fdbc9105d3f2ca08d9789089a2`. Backend/frontend CI and GHCR publishing passed; automated staging initially failed on a genuine Compose runtime issue. This issue and staging nginx permission failure were fixed after isolated local reproduction, before accepting release.
- Final workflow: `backend` + `frontend` CI → both same-SHA GHCR Images → isolated PostgreSQL 18 + Django + Next.js + self-signed HTTPS staging validation → **only if all pass**, optionally gated production release. No automatic production deployment authorized.

## Reproducible MateServer staging acceptance

- Root-only staging directory `/opt/MateERP-staging`, separate Docker Compose project `mateerp7e`, separate named volumes `mateerp7e_pgdata` and `mateerp7e_documents`, separate private/ingress networks.
- Public host bindings exclusively `127.0.0.1:13035` and `127.0.0.1:18443` (local loopback). Public port 443, ERP virtual host, DNS, certificates and existing production applications untouched.
- Pulled real GHCR images with SHA tag, **not** a locally built or development-server substitute.
- PostgreSQL 18 fresh migrations: 113 migrations. Production Django/Gunicorn and Next.js images healthy.
- Temporary TLS ingress: `https://erp.netamate.com:18443` via explicit `--resolve` to loopback and short-lived self-signed test certificate. `/login` HTTP 200; `/api/v1/health/` returned JSON status `ok`, environment `production`. CSRF endpoint HTTP 200 and Secure/SameSite cookie attributes verified. The self-signed certificate must **never** replace the existing trusted production certificate.
- Validated staged database `pg_dump -Fc`, `pg_restore --list`, SHA256 checksum, staged private-document tar SHA256, restored two independent fixture records into an isolated second database, and verified all 113 migrations persisted.
- Tested two real published GHCR image revisions, switching a7d8780 → 806e5f8 → a7d8780 on staged services, with health and synthetic database records preserved.
- Runtime findings remediated: `tmpfs` short syntax caused Docker mount path error, corrected in production and staging Compose. Staging-only nginx needed its standard master privileges to initialize a temporary writable cache; capability drop was removed **only from the disposable loopback proxy**.

## Private-repository-compatible publishing and deploy

- Repository variable `MATEERP_CI_RUNNER_LABELS` controls all CI, Image and Staging jobs, default `["ubuntu-latest"]` while public. Set `["self-hosted","linux","x64","mateerp-ci"]` after provisioning a **dedicated runner not installed on production MateServer**. Runner must be online; label configuration alone is insufficient, and free private GitHub-hosted minutes are not assumed.
- CI uses `GITHUB_TOKEN` with scoped `packages: write` to publish under `ghcr.io/rizwansammo/mateerp-frontend` and `ghcr.io/rizwansammo/mateerp-backend`.
- Staging uses `GITHUB_TOKEN` with `packages: read` to pull potentially private images on the runner.
- Future restricted SSH production deployment is designed to pass the **short-lived** `GITHUB_TOKEN` securely over standard input, using a root-only temporary `DOCKER_CONFIG` on the server. This avoids a persistent GHCR PAT. Production deploy remains gated at GitHub **and** MateServer.
- **Security reminder:** unauthenticated access to an existing GHCR image manifest succeeded on 2026-10-22. When source repo is made private, separately set both GHCR packages to private if source confidentiality is required; private GitHub repo visibility alone is insufficient. Package visibility and repo/runner secret settings require repository administration access.

## Remaining operator-controlled gates (for Phase 7F)

1. Make sure an independent dedicated self-hosted CI runner is connected and tagged `mateerp-ci`; set `MATEERP_CI_RUNNER_LABELS` **before** privatizing the repository to avoid spending or needing GitHub-hosted minutes.
2. Ensure GHCR package access is granted to the repository; change GHCR packages visibility to Private when appropriate.
3. Configure GitHub production environment secrets `MATEERP_DEPLOY_SSH_KEY`, `MATEERP_DEPLOY_KNOWN_HOSTS` and variables `MATEERP_DEPLOY_HOST`, `MATEERP_DEPLOY_PORT`, `MATEERP_DEPLOY_USER`; keep `MATEERP_AUTO_DEPLOY_ENABLED=false` until final approval.
4. Provision production secrets, restricted SSH/sudoers command, protected backup encryption keys and offsite storage; verify production Nginx using existing certificate and dedicated upstream.
5. Require a separate written production go-live approval before exposing `erp.netamate.com` or enabling either deployment gate.

**Out of scope for Phase 7E:** live production ERP startup, changing the public domain routing, making GHCR packages private using unavailable administrator permissions, or registering an external self-hosted runner that is not connected.
