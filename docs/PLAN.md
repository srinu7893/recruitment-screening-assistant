# Application status and next work

Reviewed against the code and reported deployment results on 22 October 2026.
This replaces the older phase plan, which still marked deployed features pending.

## Current process

1. **Create a role.** Approve requirements and questions. Put matching phrases
   in straight double quotes: `Experience with "SQL"`.
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

## Prioritized backlog

Develop = code change. Configure = connect existing software. Verify = test the
operating process rather than add a feature.

| Priority | Type | Next item | Definition of done |
| --- | --- | --- | --- |
| 1 | Develop | Matching-phrase fields and role preview | Show phrases per criterion; warn before approving an empty phrase set; preview matching against sample text |
| 1 | Develop | Clear source availability in Automation | Cloud Run shows upload/feed guidance; unavailable folder controls are hidden or disabled; no-source setup gives a next step |
| 1 | Develop | Team account administration and recovery | Admin can create, disable and reset individual accounts with an audit trail |
| 2 | Develop | Consistent errors and retry controls | Every failed screening job has a readable cause and an explicit retry that preserves the original and creates a new job |
| 2 | Configure + verify | One approved live feed or ATS source | Authorized imports work end-to-end; duplicates and failures are handled; polling is demonstrated live |
| 2 | Configure + verify | Alerts and backup/restore procedure | Worker/scanner/database failures raise actionable alerts; a restore exercise recovers agreed records |
| 2 | Verify | Load, restart and recruiter pilot | Agree volume and review-quality targets; document results using a representative sample and two reviewers |
| Later | Develop | Better rules interpretation | Test negation, synonyms and structured experience requirements on a labelled corpus before changing matching behavior |
| Later | Develop | Original-file storage, notifications, extra ATS mappings | Add if the pilot needs them; define retention and access for stored originals |

## Next action

- **Manager demo:** load fictional data and follow the five steps. No further
  core feature is required for a presenter-led demonstration.
- **Team pilot:** improve phrase setup and source availability, provision
  individual accounts, and agree retention and restore procedures.
- **Wider rollout:** finish monitoring, load/failure checks and recruiter
  calibration. A deployment smoke test is not an accuracy or scale test.

Review findings: [PRODUCT_REVIEW.md](PRODUCT_REVIEW.md). Presenter instructions:
[manager-demo/PROCESS.md](manager-demo/PROCESS.md).
