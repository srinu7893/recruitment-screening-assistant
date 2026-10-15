# Deployment and operations

## Neon and public HTTPS

See [NEON_DEPLOYMENT.md](NEON_DEPLOYMENT.md) for PostgreSQL persistence and the optional container recipe; see [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md) for Cloud Run/IAP, data persistence, migration and rollout limits. Set `DATABASE_URL` for PostgreSQL and `SCREENING_PUBLIC_URL` for an explicit public HTTPS origin. `/readyz` exposes status only.

## Local MVP

Use the README setup on Linux. The parser uses POSIX resource limits and process groups. The application server defaults to loopback and is intended for local development/pilot operation. Keep candidate records and credentials out of Git. The default data directory and new SQLite file are created with private OS permissions.

Docker Compose includes Python, Poppler, Tesseract and a non-root account, read-only application filesystem, temporary scratch storage, dropped capabilities, memory/PID limits, and a persisted data volume. Only the local host port is published. These are deployment controls, not a complete production security certification.

## Accounts

The simple setup uses SCREENING_API_TOKEN as the admin operator. For separate audit identities, set SCREENING_ACCOUNTS to a JSON array (values below are placeholders; replace with unique random tokens of at least 32 characters):

```json
[
  {"name":"hiring-admin","role":"admin","token":"REPLACE_WITH_A_UNIQUE_RANDOM_ADMIN_TOKEN"},
  {"name":"recruiter","role":"reviewer","token":"REPLACE_WITH_A_UNIQUE_RANDOM_REVIEWER_TOKEN"},
  {"name":"observer","role":"viewer","token":"REPLACE_WITH_A_UNIQUE_RANDOM_VIEWER_TOKEN"}
]
```

Admin: roles, ingestion, reviews, integrations, deletion, retention and audit. Reviewer: ingestion, review, comparison and notes. Viewer: read-only records. All accounts belong to the same organization; do not share one instance among unrelated companies. Rotate tokens by changing the environment and restarting. Google IAP SSO is available for cloud deployments; MFA policy is managed by the identity provider. Per-job visibility is not implemented.

## Environment variables

| Variable | Purpose/default |
| --- | --- |
| SCREENING_API_TOKEN | Simple admin token |
| SCREENING_ACCOUNTS | Optional account array; takes precedence over simple token |
| OPENAI_API_KEY / OPENAI_MODEL | Required only for live provider |
| SCREENING_PROVIDER | Provider choice, default demo; --provider overrides it |
| SCREENING_ALLOWED_HOSTS | Comma-separated exact public hostnames; empty blocks URL/feed import |
| SCREENING_WEBHOOK_SECRET | HMAC secret for incoming profile batches |
| SCREENING_CONNECTOR_URL | Fixed HTTPS JSON feed URL |
| SCREENING_CONNECTOR_TOKEN | Optional feed bearer credential |
| SCREENING_CONNECTOR_ROLE | Approved destination role version |
| SCREENING_SYNC_SECONDS | 0 disables; otherwise minimum 60 seconds |
| SCREENING_RETENTION_DAYS | 0 disables automatic expiry; otherwise 1–3650 days |

The feed role must already exist. Schedules run only while the server is running. Sync failures are visible in connection status and retry on the next configured interval; screening failures require an explicit new run to avoid hidden model charges. Retention is checked hourly. It removes eligible run/job records, not backups or separately imported copies. Failed/cancelled queue-only records keep metadata but remove profile payloads.

## Backups and restore

```sh
python -m screening.admin data/screening.sqlite3 data/backups/recruitment-backup.sqlite3
```

The destination must be new. The command uses SQLite's backup API and checks integrity. Backups contain personal data and need restricted/encrypted storage and their own expiration policy.

To restore: stop the server, retain a copy of the current database, copy a verified backup to a new private path, and start with `--db path/to/restored.sqlite3`. Never replace a database underneath a running server. Startup marks interrupted jobs failed and leaves queued jobs available. Local tests cover backing up and reopening records; a production disaster-recovery drill is still required.

## Before production rollout

Configure TLS/reverse-proxy host/origin policy, managed identity/SSO, encrypted disk and backups, retention policy, secret management, monitoring, malware scanning, model data-handling review and a recruiter-led quality pilot. Host/Origin checks accept localhost/127.0.0.1 on the bound port and the explicitly configured SCREENING_PUBLIC_URL HTTPS origin. Forwarded headers cannot expand this allowlist.

SQLite remains available locally; Neon/PostgreSQL is supported for persistent cloud records with one elected active worker and overlapping web instances. Large-volume deployments need a durable worker platform, database service, bounded retry strategy, per-organization authorization and resource monitoring. Actual provider billing is not measured by this MVP; no savings or accuracy numbers are invented.
