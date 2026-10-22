# Phase 7E — Private-Ready CI/CD & Staging

**Repository:** https://github.com/rizwansammo/MateERP. **Production:** https://erp.netamate.com, untouched until separate go-live approval.

## CI/CD progression

The same workflow handles **public and private** repositories. `main` push triggers backend and frontend CI. If both succeed, SHA-pinned frontend/backend images are built and pushed to GHCR via `GITHUB_TOKEN` with `packages: write`. Production deployment requires **both** a GitHub repository variable `MATEERP_AUTO_DEPLOY_ENABLED=true` and an independent root-owned server gate `/etc/mateerp/auto-deploy-enabled`. The latter remains ABSENT.

For private repos with insufficient GitHub-hosted minutes: use an independent, trusted **dedicated self-hosted runner** outside MateServer (e.g. an approved ThinkPad or separate build VPS). Install GitHub Actions runner according to GitHub's official per-repository setup and apply a custom label `mateerp-ci`. In Settings → Secrets and variables → Actions → Variables, set `MATEERP_CI_RUNNER_LABELS` to the literal JSON `["self-hosted","linux","x64","mateerp-ci"]`. Docker Engine and Buildx must be available to the runner service; avoid placing the runner on production infrastructure and use ephemeral/isolated runners whenever practical. Public repositories must not accept untrusted PR workflows on a reusable runner with sensitive credentials. A runner must be online to execute jobs; labels alone do not deploy anything. No self-hosted runner is registered or connected by this phase.

If `MATEERP_CI_RUNNER_LABELS` is missing, the default is `["ubuntu-latest"]` (GitHub-hosted). **Changing a repository to private does not automatically remove GitHub-hosted billing/minute limits**; users must switch the variable to a real online self-hosted runner before private builds can proceed without consuming hosted minutes.

GHCR packages can be private; ensure `rizwansammo/MateERP` has write access to both container packages under GHCR, and grant the production deployment machine a **read:packages-only** token or other approved package credentials for private pulls. Do not put PATs in git. Image names are `ghcr.io/rizwansammo/mateerp-frontend` and `ghcr.io/rizwansammo/mateerp-backend`, tagged `sha-<full commit>`. All worker labels, secrets and environment protections must be configured by a GitHub repository administrator.

## Staging limitations and go-live boundary

Run only a distinct `mateerp7e` Compose project, with separate networks, volumes, credentials and loopback-only entrypoint. **Never run `docker compose up` against the production project** or edit live Nginx for Phase 7E. All storage uses fresh fixtures; live DB/financial records are not imported. To exercise HTTPS, publish a *staging-only*, loopback-bound TLS proxy, not `erp.netamate.com:443`.

The production app still needs first-time private GHCR pull credentials, production 0600 secrets, protected SSH deploy credentials, external offsite Restic repository, full migration/backup checks and explicit Phase 7F approval. After go-live, enable both deploy gates to permit future automatic production deploys.

If the repository is set private before the self-hosted runner is available, CI jobs may queue and GHCR pushes won't occur. Keeping a token-controlled production deploy does NOT imply that GitHub-hosted minutes become unlimited.
