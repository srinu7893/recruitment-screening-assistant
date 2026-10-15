# Delivery plan and phase status

Status labels distinguish implemented/tested software from external validation. A phase is not marked fully complete if its original acceptance gate still needs a real provider, platform, or pilot.

| Phase | Shipped scope | Status | Remaining acceptance gate |
| --- | --- | --- | --- |
| 1 — Foundation | Architecture, contracts, deterministic screening, synthetic examples, CI | **Done** | None for foundation scope |
| 2 — LLM screening | Approved role versions, pasted profiles, summaries, evidence validation, SQLite, model adapter | **Implementation done; live validation pending** | Configured model/key and recruiter-reviewed quality evaluation |
| 3 — Documents | PDF/DOCX/TXT, bounded subprocess parser, English OCR, batches, duplicate-text notices, visible failures | **Done for local MVP** | Production malware scanning and broader multilingual/document corpus evaluation |
| 4 — Recruiter workflow | Responsive dashboard, scoped tokens, role editor, evidence, correction history, notes, decisions, comparison | **Done for local MVP; browser CI passed** | SSO and per-job access are outside local MVP |
| 5 — Integrations | CSV, allowlisted URL reading, signed webhooks, JSON feed, schedules, import deduplication | **Generic integration layer done** | Named ATS mapping/account credentials and real-system smoke test |
| 6 — Pilot and deployment | Container configuration, audit, metrics, retention, backups, queue recovery, tests | **Operational foundation done; container CI passed; pilot pending** | Live pilot quality targets, infrastructure security and production rollout |

## Completed features

- [x] Workflow-controlled recommendations with a separate human decision record.
- [x] Required/preferred criteria, immutable role versions and approval identity.
- [x] Editable job-description drafts; explicitly line-based rather than falsely labeled AI-generated.
- [x] Facts, summary claims, supporting excerpts and missing-evidence handling.
- [x] PDF/DOCX/TXT ingestion, English OCR for scanned PDFs, limits and safe error states.
- [x] Background jobs, duplicate request protection, cancellation and explicit recovery after crashes.
- [x] Dashboard, search/filter, queue status, decisions, reviewer notes, corrections and optimistic revisions.
- [x] Evidence comparison, interview kits, what-if required-criteria previews and talent rediscovery.
- [x] CSV, HMAC webhooks, replay prevention, HTTPS source allowlist and pinned public DNS.
- [x] Configurable JSON feed and optional timed synchronization.
- [x] Role-scoped tokens, audit log, data deletion, retention, export and verified SQLite backup.
- [x] Deployment recipe and CI coverage for API, documents, browser and container.

## Bugs found and fixed during the expansion

- Old synchronous API expectations were incompatible with background processing; submissions now return HTTP 202 and tests wait for completion.
- OCR selected a broken environment wrapper; worker selection now prefers installed system Poppler/Tesseract executables.
- Webhook replay checking had a concurrent check/insert race; claims are now atomic in SQLite.
- Concurrent reviewers could overwrite each other's work; changes now require the current revision.
- Corrected evidence could leave an outdated decision active; corrections reopen review and preserve decision history.
- Running two servers against one database could corrupt recovery behavior; a process lock prevents this.
- Shared token identities could undermine audit attribution; configured token values must be unique.

## External gates still open

- [ ] Select/configure a live model and measure correctness on recruiter-labeled examples.
- [ ] Verify one real ATS feed/webhook mapping with the owner's credentials.
- [ ] Agree numeric quality targets and run a recruiter pilot.
- [ ] Configure production identity, TLS, encrypted storage, backup retention and access review.
- [ ] Add malware scanning, multilingual OCR and large-volume worker infrastructure if required.

Do not mark these gates done merely because an adapter, mock test or deployment file exists.

## Production-support showcase phase — Done

- [x] Six original fictional resumes with evidence-validated authored summaries and expected routing.
- [x] Public reference PDF reviewed; source link and short summary recorded without redistributing the PDF.
- [x] Offline interactive dashboard, resume downloads, scenario filtering and guided manager walkthrough.
- [x] Admin-only idempotent demo loading, named profile search and per-role criterion gap metrics.
- [x] Regression coverage for fixture integrity, demo decision restrictions, permissions and invalid comparison IDs.

External acceptance gates above remain unchanged.

## Cloud persistence and team operations phase

- [x] PostgreSQL/Neon adapter, verified TLS and direct-session ownership fencing.
- [x] Persistent roles, jobs, results, reviewer history, assignments and audit.
- [x] Transactional SQLite-to-empty-PostgreSQL migration with source preservation.
- [x] Explicit public HTTPS origin, runtime PORT/provider configuration and readiness endpoint.
- [x] Reviewer assignment, priority, UTC due dates, overdue/mine filters and team workload.
- [x] Dedicated PostgreSQL CI service and regression tests; deployment recipe with maintenance window.
- [ ] Live Neon credentials/host connection and restart smoke test.
- [x] Cloud Run overlapping-revision implementation with elected PostgreSQL worker and fenced writes; live rollout verification still pending.
- [x] Verified Google IAP SSO implementation and identity tests.
- [ ] Live IAP/MFA policy, tenant isolation, production document scanning and live-model pilot.

## Cloud workspace phase

- [x] Cloud Run refuses ephemeral SQLite; PostgreSQL remains the source of truth.
- [x] Leader/standby workers, takeover recovery and interrupted-call fencing.
- [x] Manual deployment workflow with WIF, pinned Secret Manager versions and immutable images.
- [x] Google IAP signature/issuer/audience/expiry validation and approved subject-role mapping.
- [x] Visual command center, review board, intake trends, source channels and runtime status.
- [x] Cloud-hosted model-evaluation workflow and fictional regression report.
- [ ] Provision actual cloud resources and validate the deployed URL with real identity and Neon credentials.

These code-completion marks do not mean that live deployment, ATS access, model quality or security certification has been completed.

## Advanced review and ingestion phase

- [x] Read-only Greenhouse Harvest v3 selected-resume OAuth adapter with candidate association checks and safe downloads.
- [x] Fail-closed ClamAV scan gate, signature-age checks, cloud sidecar image and deployment wiring.
- [x] Structured interview evidence with role-linked criteria, author history and decision reopening.
- [x] Per-criterion model diagnostics, status confusion counts, routing agreement and human review rubric.
- [x] URL imports share the bounded parser capacity with manual/ATS uploads.
- [ ] Verify real Greenhouse account permissions, attachment hosts and authorized sample import.
- [ ] Verify cloud scanner startup, signature updates and blocked-file smoke tests.
- [ ] Complete representative recruiter-labeled live-model pilot and agree release thresholds.

See `ADVANCED_WORKFLOWS.md` for setup and acceptance boundaries. Multilingual OCR, high-volume ATS crawling and multi-tenant authorization are future scope; each deployment continues to serve one organization.
