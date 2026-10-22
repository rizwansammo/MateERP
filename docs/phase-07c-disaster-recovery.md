# MateERP Phase 7C: Encrypted Backup & Disaster Recovery

**Status:** Prepared and isolated-test verified, NOT installed or enabled on production.  
**Base code:** a836163e1df89619d05c7a226f93b769bd0b9c88 (Phase 7A/7B uncommitted source changes included).  
**Production target:** erp.netamate.com, /opt/MateERP, PostgreSQL 18, private Docker document volume.

## Assets and protection model

1. **PostgreSQL 18:** `pg_dump -Fc` consistent database snapshot. `pg_restore --list` verifies archive structure before upload. Service-owned database and named volume remain untouched.
2. **Private files:** read-only mount of MateERP's dedicated `mateerp_documents` Docker volume into an isolated container without a network; archived as `documents.tar`.
3. **Configuration:** `.env.production` (contains credentials) and `compose.production.yml` are copied into the protected temporary bundle, then included in a Restic-encrypted snapshot. They are never exposed to CI or printed to logs.
4. **Integrity:** SHA256SUMS includes the database dump, documents archive, app configuration, and manifest. Recovery checks all hashes before extraction.
5. **Encryption:** dedicated Restic password stored in `/etc/mateerp/restic-password` (0600), never in the repo or in its own encrypted backup.
6. **Offsite:** separate Restic repository and key at independent off-server storage. `restic copy` verifies offsite access. Provision the account/provider, endpoint, access and recovery key separately; **no offsite credentials exist yet**.

**Security caveat:** Temporary database dumps and `.env.production` staging copies exist in root-only mode while a snapshot is being produced; normal completion cleans them up. The host disk is not guaranteed to be encrypted; unexpected power loss may leave a root-only `.stage-*` directory requiring secure administrative cleanup. Disk-at-rest encryption for backup staging and monitoring of stale staging directories should be included in production acceptance.

**Consistency caveat:** PostgreSQL's dump is consistent, but document files are read at a slightly later time. If a document is removed or altered between steps, a DB/file mismatch is possible. The files service ordinarily preserves immutable official documents, but an actual production-style consistency drill and DB-reference verification are required before the final go-live decision. A maintenance/write-quiescence window is preferable for the first production snapshot.

## Planned timers (NOT ENABLED)

| Service | Local business schedule | Purpose |
|---|---|---|
| mateerp-backup.timer | Daily 02:15 Asia/Dhaka, 0-5 minute jitter | Encrypted local snapshot, then mandatory offsite copy |
| mateerp-retention.timer | Sunday 04:15 Asia/Dhaka, 0-15 minute jitter | Local retention and 1/20 data read-integrity check |

The VPS uses Europe/Berlin timezone; timer calendar expressions explicitly include **Asia/Dhaka**. Scheduled tasks have intentionally not been installed. Final timing must be assessed against real low-traffic and other apps before enablement.

Retention design: 7 daily, 4 weekly, 6 monthly, 2 yearly snapshots **for the dedicated MateERP local repository**. Offsite retention lifecycle needs separate provider-specific setup and acceptance; never prune shared storage.

**Recovery objectives:** Designed for roughly one-day backup intervals; actual RPO depends on successful backup/offsite completion and alarms. No proven production RTO yet. A quick fixture restore does NOT establish production restore duration.

## Provisioning at approved first go-live only

These are controlled steps, **not commands executed during 7C**:

1. Review and merge the uncommitted scripts from `deploy/backup/` into the official repository, after authorized Git workflow and CI.
2. Install `mateerp-backup.sh`, `mateerp-offsite-copy.sh`, `mateerp-retention.sh` and `mateerp-restore-drill.sh` as root-owned executable `0700` files in `/usr/local/sbin`, after independent code review.
3. Create `/etc/mateerp` root-owned mode `0700`; provision unique high-entropy Restic local and offsite password files, each `0600`; separately escrow encryption recovery keys in the company password manager/offsite secure vault. **Without these keys backup recovery is impossible.**
4. Copy and configure `backup.env.example` as root-only `/etc/mateerp/backup.env` mode `0600`. Provision access to a genuinely remote offsite provider, ideally minimum-permission write/read credentials and retention protection. Keep all secrets outside Git/GH Actions output.
5. Initialize dedicated local repository with `RESTIC_REPOSITORY=/opt/MateERP/backups/repository RESTIC_PASSWORD_FILE=/etc/mateerp/restic-password restic init`; separately initialize offsite repository using its own credentials and key. Verify access and listing **before enabling** any timer.
6. Test a real production-style backup in a private staging deployment, including document links and immutability. Test recovery **only into an isolated container**, then check counts, issued-document snapshots, ownership approvals, journal balance, idempotency and fiscal locks.
7. Enable `/etc/mateerp/backup-enabled` only after explicit operational approval and successful staging verification. Install service/timer units and `systemctl daemon-reload`. Enable timers only at the go-live approval gate. Include alerting on missed runs and failed offsite copy.
8. On failures, investigate without purging or restoring production volumes automatically.

## Recovery procedure

1. Locate the last confirmed successful **offsite** snapshot and preserve incident evidence. Recover the separately escrowed offsite encryption key on a trusted replacement host.
2. Provision a new isolated PostgreSQL 18 instance and isolated document storage (never point recovery tests at the production database/volume). Do not expose its PostgreSQL port publicly.
3. List Restic snapshots, choose an explicitly identified snapshot ID and restore to a root-only directory. Verify SHA256SUMS **before importing**.
4. Run `mateerp-restore-drill.sh <snapshot-id>` in an approved isolated recovery environment using temporary credentials; its implementation refuses production restore and creates a short-lived Docker DB with `--network none`.
5. Inspect recovered files, database schema, migrations, journal balances and posted record immutability. Use strict extraction (regular files/directories only, reject path traversal and symlinks).
6. For actual service recovery, prepare a new deployment, back up any present target first, obtain owner approval for cutover and migration, then perform separately reviewed production restore. **No automatic overwrite, delete, or rollback of financial records.**
7. Verify application authentication, permissions, financial statements, customer invoices and PDFs, offsite backup continuity, HTTPS/DNS and unrelated MateServer applications.

## Actual Phase 7C acceptance results (isolated fixture)

- Self-contained fixture: PostgreSQL 18, two distinct records, one private document, config metadata, SHA256 manifest.
- Encrypted local Restic backup: **passed**.
- Independently encrypted second Restic repository and copy: **passed**.
- Offsite Restic integrity check: **passed**.
- Offsite snapshot restore and SHA256 validation: **passed**.
- Safe document extraction and isolated networkless PostgreSQL restore: **passed after a correction** to the test container's UID 70 data-directory permissions.
- Real-data sample fixture contents are checked by the recovery test; no real financial production data exists yet to exercise.
- Security gate negative tests: backup/offsite/retention scripts refuse execution without authorization; invalid restore snapshot refused.
- No MateERP production containers or timers installed, no live ERP host change except previously staged inert Compose file.

**Pending for operational sign-off:** real offsite provider and secret provisioning, successful unattended backup on staging, restore from full application DB/actual private documents, monitoring/alerting, proven real-life RPO/RTO, and approved first go-live. These remain later-stage gates; do not call the backup system active yet.
