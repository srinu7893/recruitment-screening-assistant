# Cloud workspace: Cloud Run + Neon + Google IAP

The normal recruiter workflow is browser-only: open the cloud URL, sign in through Google IAP, upload/paste/import profiles, review summaries, assign work and monitor the command center. No database or application server needs to run on a recruiter's laptop.

## Cloud components

- GitHub Actions tests and builds the application, then performs an explicitly requested deployment.
- Artifact Registry holds immutable container images.
- Cloud Run serves the interface/API with instance-based CPU and at least one instance for background work.
- Neon stores roles, extracted profile text, queue entries, results, notes, decisions, assignments and audit history. Cloud Run refuses to fall back to ephemeral SQLite.
- Secret Manager supplies the database URL, approved IAP account mappings and optional model key. Secret values are never written to release manifests.
- Google IAP handles browser authentication. The application independently verifies signed assertions, their issuer, audience, expiry and approved subject-to-role mapping. Unsigned email headers and workspace bearer tokens cannot bypass IAP mode.

## First-time cloud setup (console + GitHub, no local app)

1. Select your GCP project/region. Enable Cloud Run, Artifact Registry, Secret Manager, IAP and IAM credentials APIs. Create an Artifact Registry Docker repository and a dedicated runtime service account.
2. Create a dedicated Neon recruitment database. Save its direct PostgreSQL URL as a Secret Manager secret, using `sslmode=verify-full` and a pinned secret version. Do not reuse the payment app's database role.
3. Bootstrap a private Cloud Run service slot in the console to obtain its canonical HTTPS URL. Enable IAP using the console's identity/OAuth setup. Do not add anonymous invoker access. Grant the IAP service agent permission to invoke the service and grant approved users the appropriate IAP access role.
4. Record the exact IAP resource audience from your IAP configuration. Create the approved account mapping below using stable verified subjects, not an email domain wildcard. Store it in Secret Manager. Apply organizational MFA/access policy at the identity provider if required; the application does not claim to enforce MFA itself.
5. Allow the runtime service account to read only the required secret versions. Configure GitHub Workload Identity Federation for this repository, main branch and environment. Grant the deployer Cloud Run deployment, Artifact Registry write and runtime-account act-as permissions.
6. Create GitHub environment `recruitment-cloud`. Add secrets `WIF_PROVIDER` and `GCP_SERVICE_ACCOUNT`. Add variable `CLOUD_RUN_CONFIG_JSON` using `deploy/cloud-run/config.example.json`, replacing every placeholder with your own resources and pinned secret versions.
7. Wait for **Tests** to pass on main. Run **Actions → Deploy recruitment cloud → Run workflow**. It validates configuration, builds/pushes web and scanner images, resolves their digests, creates a ready revision and promotes it. For an existing service, its current traffic is pinned during candidate startup.
8. Open the canonical cloud URL, sign in as an approved account, load fictional profiles, inspect the command center, upload a TXT/PDF and record a hold. Repeat after a redeploy to confirm persistence. Review Cloud Run logs, worker status and the release artifact.

Example account mapping (replace the subject with the actual verified identity):

```json
[
  {"subject":"accounts.google.com:ACTUAL_STABLE_SUBJECT", "name":"Hiring admin", "role":"admin"},
  {"subject":"accounts.google.com:ANOTHER_STABLE_SUBJECT", "name":"Recruiter", "role":"reviewer"}
]
```

The exact audience must match the IAP resource protecting this service. A wrong audience or unknown subject is rejected. Approved viewer accounts can inspect records but cannot mutate them. Each deployment is one organization; separate organizations need separate databases/services until tenant-level authorization is implemented.

## How overlapping revisions work

Every revision can serve authenticated requests against Neon. Each background worker attempts the same PostgreSQL session advisory lock; only its owner screens profiles. Others remain ready as standby workers. The leader processes queued work and runs scheduled feed/retention tasks. When it stops or loses its connection, another revision can acquire ownership.

The owning database session is also the session used for writes. A disconnected old worker cannot write through a surviving second connection. On takeover, jobs that were in progress are marked interrupted and require explicit retry, preventing silent repeat model charges. Queued jobs persist. Interrupted paid calls can still incur provider charges even when their result cannot be saved; this is not an exactly-once external API guarantee.

**Drain the queue before changing model/provider configuration.** Jobs record the configuration at submission; an incompatible worker fails them explicitly. Normal image rollouts with unchanged provider configuration support overlapping revisions. Schema changes must remain backward-compatible during rollout; this release only adds compatible application behavior.

Startup probes check application/database readiness. Standby workers are healthy: another instance owns processing. Cloud Run can terminate a worker during a model call; the application fences late writes and preserves interrupted status rather than pretending the call completed.

## Command center

- Seven-day intake chart, source channels and pending-review age groups.
- Four-column review board with names, owners, role versions and demo labels.
- One-click overdue, unassigned and processing-failure queues.
- Database, identity and per-instance worker status.
- Existing evidence summaries, comparison, interview kits, what-if requirements, notes, corrections and audit history remain available.

Numbers describe recorded workflow activity, not candidate quality or claimed productivity savings. Demo mode and authored showcase data remain visibly labeled.

## Cloud model evaluation

Create GitHub environment `recruitment-evaluation` with secret `OPENAI_API_KEY`. Run **Evaluate live screening model** and supply your supported model ID. This makes paid model calls on six fictional production-support resumes and uploads a JSON report with valid-output counts, criterion agreement, differences and routing.

The small authored corpus is a regression check. Quote matching validates provenance, not semantic correctness. Invalid outputs are counted separately and excluded from agreement calculations. No score automatically approves a model or changes a hiring decision. A broader recruiter-labeled pilot remains necessary.

## Integrations and remaining external gates

The HTTPS feed, signed webhook, CSV and URL ingestion layers already run in the cloud. A real ATS still needs provider-specific field mapping and account credentials; arbitrary vendors are not claimed to work automatically. IAP protects the service edge, so an ATS webhook caller must also satisfy that edge's machine-access policy; scheduled authenticated feed polling is an alternative. Do not disable IAP globally to admit a webhook.

The following cannot be marked verified by committing code: live GCP/Neon/IAP provisioning, authenticated browser smoke testing, a real ATS mapping, production document malware scanning, tenant isolation, backup/restore drills and recruiter acceptance of live model output. Original uploads are temporary; this release does not provide a cloud original-document archive.

## Rollback and monitoring

Release artifacts contain the image/revision manifest and previous traffic allocation. Restore the saved explicit revisions through Cloud Run's traffic controls if a release has a functional issue. Candidate startup failures preserve existing traffic. Promotion itself does not test an end-user's IAP entitlement; complete the authenticated smoke test. Database changes and external model charges are not reversed by traffic rollback.

Monitor Cloud Run readiness/errors, Neon capacity, job failures and overdue reviews. The service uses always-allocated CPU and a minimum instance for background processing; budget for these resources. Keep secret versions, backup retention and access policy under your organization's control.

## Official setup references

- [Cloud Run IAP setup](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [IAP signed assertions](https://docs.cloud.google.com/iap/docs/signed-headers-howto)
- [Cloud Run runtime lifecycle](https://docs.cloud.google.com/run/docs/container-contract)
- [Neon verified connections](https://neon.com/docs/connect/connect-securely)
