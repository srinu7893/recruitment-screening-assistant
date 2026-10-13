# Delivery plan and phase status

Status labels distinguish implemented/tested software from external validation. A phase is not marked fully complete if its original acceptance gate still needs a real provider, platform, or pilot.

| Phase | Shipped scope | Status | Remaining acceptance gate |
| --- | --- | --- | --- |
| 1 — Foundation | Architecture, contracts, deterministic screening, synthetic examples, CI | **Done** | None for foundation scope |
| 2 — LLM screening | Approved role versions, pasted profiles, summaries, evidence validation, SQLite, model adapter | **Implementation done; live validation pending** | Configured model/key and recruiter-reviewed quality evaluation |
| 3 — Documents | PDF/DOCX/TXT, bounded subprocess parser, English OCR, batches, duplicate-text notices, visible failures | **Done for local MVP** | Production malware scanning and broader multilingual/document corpus evaluation |
| 4 — Recruiter workflow | Responsive dashboard, scoped tokens, role editor, evidence, correction history, notes, decisions, comparison | **Implementation done; browser acceptance in CI** | Real-browser CI must pass; SSO is outside local MVP |
| 5 — Integrations | CSV, allowlisted URL reading, signed webhooks, JSON feed, schedules, import deduplication | **Generic integration layer done** | Named ATS mapping/account credentials and real-system smoke test |
| 6 — Pilot and deployment | Container configuration, audit, metrics, retention, backups, queue recovery, tests | **Operational foundation done; pilot pending** | Container CI, live pilot quality targets, infrastructure security and production rollout |

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
