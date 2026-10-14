# Deploy the recruitment workspace with Neon

## What works, and what GitHub does

GitHub stores the code and runs the automated tests. GitHub Pages can host only the offline showcase; it cannot run the Python API, document parsing or background screening. Run the full app as a Linux container behind HTTPS. `DATABASE_URL` selects PostgreSQL; without it, the app uses the existing local SQLite database.

The owner's `otel-payment-platform-poc` deployment guide uses Docker, Cloud Run, WIF and Secret Manager, with Neon as an external database. This app follows the same separation of code, runtime configuration and database secrets. No project IDs, service accounts, secrets or deployment permissions were copied. The payment deployment's overlapping revision rollout is **not compatible with this single-worker release**.

## Recommended supported topology

One Linux VM/container host with an HTTPS reverse proxy → one recruitment container → a dedicated Neon database. Use your existing proxy or platform TLS edge. It must preserve the public Host header. Set `SCREENING_PUBLIC_URL` to that exact HTTPS origin; arbitrary Host/Origin requests stay blocked. The app does not trust forwarded headers. Publish only the proxy publicly; the Compose port binds to loopback.

Create a separate Neon database/role for recruitment data. Copy the **direct, unpooled** PostgreSQL connection URL from Neon and set `sslmode=verify-full` (retain `channel_binding=require` if supplied). This release uses a session advisory lock to prevent competing workers; transaction-pooler URLs are rejected. The container includes the system CA bundle. Use an app role limited to this database, not another application's owner credentials.

1. Clone this repository on the container host.
2. Copy `.env.example` to `.env`, replace the placeholders and restrict file access with `chmod 600 .env`. On managed infrastructure, inject equivalent values from Secret Manager instead.
3. Set a unique random `SCREENING_API_TOKEN`, or configure `SCREENING_ACCOUNTS` for individual reviewer/admin/viewer identities.
4. Configure DNS, HTTPS and the proxy for your chosen hostname.
5. Build: `docker compose -f compose.neon.yaml build`.
6. For an upgrade, stop the old application first: `docker compose -f compose.neon.yaml down`. This intentionally has a maintenance window.
7. Start: `docker compose -f compose.neon.yaml up -d`.
8. Check `/readyz` through HTTPS, sign in, create a test role and run a fictional sample. Restart the container and verify that the same records remain.

Use the same Neon project/branch/database after redeployment. Roles, extracted resume text, results, jobs, notes, assignments, decisions, corrections and audit events live in PostgreSQL. Uploaded original files remain temporary and are not archived. Environment tokens and model keys remain in your secret configuration. Removing the container does not delete Neon records; application deletion/retention or deleting the Neon database does. Backups, restore windows and independent exports need their own retention policy.

## Existing SQLite records

Stop both source and destination application instances. Take a verified SQLite backup first. With the target `DATABASE_URL` injected, run:

```sh
python -m screening.migrate --source data/screening.sqlite3
```

The target must be empty. The migration locks both stores, copies all five tables in one target transaction, preserves IDs/history, and never removes the source. It refuses an occupied target. Verify counts and representative records before starting the app on Neon. Interrupted screening remains subject to startup recovery; it is not silently rebilled.

## Runtime settings and health

- `DATABASE_URL`: direct PostgreSQL URL; remote hosts require certificate/hostname verification.
- `SCREENING_PUBLIC_URL`: one HTTPS origin, such as `https://recruitment.example.com`.
- `PORT`: runtime listening port, default 8000. Container binds `0.0.0.0`.
- `SCREENING_PROVIDER`: `demo` or `openai`; live also needs `OPENAI_API_KEY` and `OPENAI_MODEL`.
- `GET /readyz`: public, status-only readiness; checks database and worker availability, without exposing configuration or candidate data.
- `GET /health`: authenticated identity/provider/database type.

A lost database ownership session fails closed. Readiness becomes unhealthy; restart the service after connectivity is restored. The app never transparently replays a paid screening call. Queued jobs persist; interrupted jobs require explicit retry with a new ID. Monitor health and configure your host to restart unhealthy containers; Docker's restart policy alone does not restart a merely unhealthy process.

## Cloud Run caveat and next platform phase

Cloud Run is not marked ready for a standard rolling deployment. Its overlapping revisions and restarts require a separate leased-worker/leader design before safe zero-downtime operation. Setting maximum instances to one alone does not solve revision overlap. Background work also needs an appropriate CPU allocation/minimum-instance configuration. Do not copy the payment app's candidate rollout unmodified. The provided Compose recipe supports a controlled stop-before-start deployment today.

SSO/MFA, organization isolation, horizontal workers, malware scanning and recruiter-validated live model quality remain separate gates. PostgreSQL persistence is not a claim that these are complete.

## References

- [Neon secure connections](https://neon.com/docs/connect/connect-securely)
- [Neon pooling limitations](https://neon.com/docs/connect/connection-pooling)
- [Existing payment deployment pattern](https://github.com/srinu7893/otel-payment-platform-poc/blob/main/docs/SERVICE_BY_SERVICE_DEPLOYMENT.md)
