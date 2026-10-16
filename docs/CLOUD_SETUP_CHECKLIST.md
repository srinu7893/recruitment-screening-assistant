# Cloud setup handoff — 16 October 2026

## Details found in the other repository

Read-only inspection of `../otel-payment-platform-poc` found these checked-in deployment values:

| Item | Discovered value | Evidence |
| --- | --- | --- |
| GCP project | `project-c9bd3d0e-266f-47bf-852` | Payment deployment workflow and bootstrap config |
| Region | `us-central1` | Payment image registry and bootstrap config |
| Existing payment image repository | `otel-payment-platform` | Payment deployment workflow |
| GitHub owner | `srinu7893` | Both repository remotes |
| Recruitment repository | `srinu7893/recruitment-screening-assistant` | This repository's remote |
| Existing CI authentication pattern | `WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT`, environment `gcp-poc` | Payment workflows |

Cloud Shell output supplied by the owner confirms billing is enabled, project number `52916499838`, Neon secrets `neon-jdbc-url`, `neon-username`, `neon-password` each at enabled version `1`, and active `otel-github-pool`/`github-pool`. Neither provider currently permits this repository. No payment service, account or database was changed. Existing GitHub environment secrets are not automatically available in another repository.

The owner elected to reuse the existing Neon database. Set `database_schema` to `recruitment` in the release config (`SCREENING_DB_SCHEMA` at runtime), provision that schema first, and use a dedicated recruitment login. Every PostgreSQL connection uses that schema without a `public` fallback; schema-specific worker/transaction locks allow independent workspaces in the same database. Namespace separation does not replace database grants: the new login should own only its recruitment schema. Existing installations default to `public` for compatibility; switching schema does not move old records automatically.

## What you need to set up

1. **Project and billing.** Confirm the project above is the intended one and billing remains enabled. In Cloud Shell, retrieve its numeric project number:

   ```sh
   gcloud projects describe project-c9bd3d0e-266f-47bf-852 --format='value(projectNumber)'
   ```

2. **Recruitment resources.** Enable Cloud Run, Artifact Registry, Secret Manager, IAP, IAM, IAM Credentials and Security Token Service APIs. Create Docker repository `recruitment` in `us-central1` and service account `recruitment-runtime`. The runtime account needs Secret Manager access to the recruitment secrets only. The deployer needs Cloud Run deployment permissions, Artifact Registry write and permission to act as that runtime account.

3. **Persistent database.** Reuse the existing Neon database with a new `recruitment` schema and login. Save that login's direct PostgreSQL URL, using `sslmode=verify-full`, in a recruitment-specific Secret Manager secret. Do not modify payment credentials or its default search path. Cloud Run uses PostgreSQL for profiles, roles, jobs, reviews, audit, automation settings and intake receipts; its filesystem is not the database. Arrange database backups and a restore drill.

4. **Google sign-in.** Bootstrap a private Cloud Run service in the console, enable IAP and record its canonical `https://...run.app` URL. Grant IAP access to approved admin/reviewer/viewer Google identities. For personal Gmail or users outside the project's organization, configure external OAuth/IAP access in the console. The app also needs approved stable IAP `sub` values mapped to names and roles, stored as a Secret Manager JSON value. Use the actual verified subjects, not a guessed email-derived value. See `CLOUD_WORKSPACE.md` for the mapping format.

5. **GitHub deployment identity.** Create environment `recruitment-cloud` in `srinu7893/recruitment-screening-assistant`. Add its `WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT` references. An existing provider can be used only if its attribute condition and service-account IAM binding explicitly permit this recruitment repository/main branch/environment. Do not broaden payment repository permissions to every repository.

6. **Demo release config.** Copy `deploy/cloud-run/config.discovered.example.json`, replace the numeric project number and canonical URL, and verify the secret names/versions match your resources. Save the JSON as GitHub environment variable `CLOUD_RUN_CONFIG_JSON`. The example intentionally fails validation until placeholders are replaced. The deployment workflow supplies the immutable scanner image digest automatically.

7. **Live screening.** For a separate real workspace, create another Cloud Run service and isolated database/secret set. Set `provider` to `openai`, add your chosen supported `model` and a pinned `OPENAI_API_KEY` Secret Manager reference. Demo mode processes arbitrary resumes to demonstrate workflow, but does not assess qualifications; its authored examples remain labeled and decisions are hold-only. The live workspace uses the configured model and human review.

8. **Automatic sources.** Browser upload/paste/CSV works without an ATS account. For automatic JSON-feed polling, set `allowed_hosts` and `connector_url` in release config, and add a `SCREENING_CONNECTOR_TOKEN` secret reference if needed. After deployment, create an approved role and configure Automation in the app. For Greenhouse, provide the dedicated read-only OAuth client secrets and exact attachment hosts. A laptop inbox is local-only; Cloud Run does not watch your laptop or use an ephemeral folder as durable intake.

Keep secret values in Secret Manager/GitHub settings. Share only project number, resource names, service URL, chosen model, approved users and the source type back in chat.

## Release and demonstration

Wait for this commit's **Tests** workflow to pass, then manually run **Deploy recruitment cloud** on main. It builds the application and ClamAV sidecar, pins image digests and secret versions, deploys a candidate revision and preserves previous traffic during startup. No deployment was performed from this workstation: Google Cloud CLI is absent and cloud credentials/resources have not been verified.

After release, complete these checks through the authenticated cloud URL:

- An approved admin signs in; an unapproved user is rejected.
- Load the demo profiles, create a role, upload a synthetic TXT/PDF and inspect its evidence and review record.
- Import from the configured source, wait for background screening and inspect Automation history. Repeating the same import creates no duplicate jobs.
- Add notes, an interview scorecard, an assignment/due date and a hold decision; verify audit and JSON export.
- Redeploy and confirm records/settings persist, only one PostgreSQL worker owns screening and queued work continues.
- Check scanner startup and fresh signatures; verify blocked uploads and model failures are visible.
- For live screening, evaluate recruiter-labeled examples before real hiring use. Verify backup restore and retention separately.

The current design uses minimum one instance and always-allocated CPU for background work, plus a ClamAV sidecar (web: 1 CPU/1 GiB; scanner: 1 CPU/3 GiB per instance). These create ongoing hosting costs; set a billing budget and alerts before launch. Google sign-in setup, real source credentials and model quality cannot be validated by local tests.

## Current official references

- [Cloud Run IAP, including external/no-organization users](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [Signed IAP assertions and Cloud Run audience format](https://docs.cloud.google.com/iap/docs/signed-headers-howto)
- [Cloud Run billing and background CPU](https://docs.cloud.google.com/run/docs/configuring/billing-settings)
- [Minimum instances](https://docs.cloud.google.com/run/docs/configuring/min-instances)
- [GitHub Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
