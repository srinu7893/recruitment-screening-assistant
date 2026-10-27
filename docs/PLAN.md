# Application status and next work

## Operations follow-up — 27 October 2026

The 23 October main commit passed CI. No subsequent deployment workflow run was
found during this review. New work adds authenticated live checks for team
accounts, recovery, viewer permissions, phrase preview and operations, plus an
opt-in daily encrypted backup workflow. Code availability does not establish live
verification. Deployment and backup configuration are separate steps. See
[SCHEDULED_BACKUPS.md](SCHEDULED_BACKUPS.md).

Remaining rollout work needs external access: release the feature code, supply
one approved live source and notification channel, configure private backup
storage/key access, and run the live smoke, restore and workload checks. There is
no unimplemented item among the original five priority code requests. Optional
future capabilities below require a pilot need and separate acceptance criteria.

## Team workflow release — 23 October 2026

The following is implemented in code and under release validation. It is not
marked live until the Cloud Run workflow and post-deployment checks pass.

| Requested item | Implementation | Remaining external step |
| --- | --- | --- |
| Easier matching | Separate phrase fields, empty-phrase warning/approval guard and unsaved sample preview; quoted legacy roles preserved | Deploy the release |
| Available sources | Unavailable folder/feed controls hidden; schedule disabled without a source; uploads remain independent | Deploy the release |
| Individual accounts and recovery | Admin create/update/disable, last-admin guard, password change, one-use 15-minute recovery, operator emergency recovery | Deploy; use individual accounts; email delivery is not part of this release |
| Errors and retry | Readable errors, explicit linked retries, duplicate-click protection, source preservation before a run exists | Deploy and check a synthetic failed-job retry |
| Real source | Approved-feed configuration CLI and existing ingestion/deduplication | Supply an approved URL and credential reference; deploy and verify a real import |
| Operations | Worker heartbeat, queue/scanner checks, content-free logs, alert installer, encrypted backup, isolated restore drill and synthetic workload client | Supply a notification channel; verify actual delivery and run the Neon/cloud drills |

See [TEAM_WORKFLOWS.md](TEAM_WORKFLOWS.md) for the exact user and Cloud Shell steps.
The dated review below records the earlier live baseline; its development
backlog is superseded by this release-status table.

Reviewed against the code and reported deployment results on 22 October 2026.
This replaces the older phase plan, which still marked deployed features pending.

## Current process

1. **Create a role.** Approve requirements and questions. Put matching phrases
   in the matching-phrase fields and preview them against sample text. Previously
   approved roles with quoted phrases remain compatible.
2. **Add resumes.** Select the role, then upload PDF/DOCX/TXT files or paste text.
3. **Check processing.** Uploads are scanned and text is extracted; the background
   worker processes saved jobs and prepares evidence reviews.
4. **Review evidence.** Read each excerpt in context. Correct an assessment with
   a reason when needed. A phrase mention is partial evidence, not a qualification.
5. **Save the next step.** Assign a reviewer, add notes and record advance, hold
   or reject with a reason. Review history stays with the record.

No model API is required. Missing text does not establish that someone lacks a
skill. The rules engine does not calculate experience duration, interpret
negation or synonyms, or automatically mark criteria met.

## Status

| Area | Current status | Evidence or limit |
| --- | --- | --- |
| Cloud Run and Neon | Deployed; live smoke test passed | Reported publication verified login, persistence, upload, worker, notes, export, deletion and logout |
| Password login | Deployed | Admin/reviewer/viewer roles; hashed passwords, expiring sessions and CSRF protection |
| Document processing | Deployed; clean upload path tested live | PDF/DOCX/TXT, ClamAV gate and bounded parser; OCR and scanner checks also run in CI |
| Local rules matching | Deployed | Finds exact approved phrases and source lines; all matches require review |
| Review workflow | Implemented and tested | Corrections, notes, assignments, scorecards, comparison and decisions; not every advanced path was tested live |
| Source ingestion | Implemented and tested | CSV, allowlisted URLs, signed webhook, feed and selected Greenhouse resume adapter; no live feed/ATS connection verified here |
| Local folder watcher | Implemented and tested locally | Not supported as a Cloud Run folder source |
| Manager demo kit | Built and tested | Five fictional profiles; HTML/PDF briefing; loader tested twice without duplicates. Live loading still needs the admin-run command |
| OpenAI adapter | Implemented; unused in this deployment | No API account/key; model quality is not validated |
| Google IAP | Legacy optional mode | Production uses application login; IAP is not a rollout requirement |

## Remaining rollout work

The original priority development items are implemented in the release table
above. These tasks connect and verify the operating application.

| Priority | Type | Next item | Definition of done |
| --- | --- | --- | --- |
| 1 | Deploy + verify | Release the team workflow features | Main CI passes, deployment succeeds, extended authenticated smoke test passes |
| 2 | Configure + verify | One approved live feed or ATS source | Authorized imports work end-to-end; duplicates and failures are handled; polling is demonstrated live |
| 2 | Configure + verify | Alerts and scheduled backup/restore | Worker/scanner/database failures raise actionable alerts; daily encrypted upload and an isolated archive restore succeed |
| 2 | Verify | Load, restart and recruiter pilot | Agree volume and review-quality targets; document results using a representative sample and two reviewers |
| Later | Develop | Better rules interpretation | Test negation, synonyms and structured experience requirements on a labelled corpus before changing matching behavior |
| Later | Develop | Original-file storage, notifications, extra ATS mappings | Add if the pilot needs them; define retention and access for stored originals |

## Next action

- **Manager demo:** load fictional data and follow the five steps. No further
  core feature is required for a presenter-led demonstration.
- **Team pilot:** deploy the implemented phrase/source/account changes, provision
  individual accounts, and agree retention and restore procedures.
- **Wider rollout:** finish monitoring, load/failure checks and recruiter
  calibration. A deployment smoke test is not an accuracy or scale test.

Review findings: [PRODUCT_REVIEW.md](PRODUCT_REVIEW.md). Presenter instructions:
[manager-demo/PROCESS.md](manager-demo/PROCESS.md).
