# Delivery plan

## Product goal

Give recruiters consistent summaries and evidence-based comparisons against approved job requirements. Automate ingestion and processing; retain human responsibility for advancement and rejection. Missing information is not a failed requirement.

## Architecture decision

Use a controlled workflow with bounded LLM steps. The workflow owns status, retries, validation and routing. The model extracts and evaluates context against a fixed criteria version; it cannot alter criteria, execute instructions inside resumes, send messages, or change ATS hiring status. Start with one service and a worker before considering multiple autonomous agents.

## Milestones and acceptance gates

| Phase | Features | Acceptance gate | Status |
| --- | --- | --- | --- |
| 1 | Plan, architecture, structured assessment core, synthetic example, CI | Local tests and sample CLI pass | Implemented in foundation |
| 2 | Approved role configuration, pasted profile, LLM adapter, grounded summaries and assessments | End-to-end profile-to-review on synthetic samples; invalid model output fails safely | Implemented locally; live-model quality gate pending |
| 3 | PDF/DOCX uploads, file limits, scan/OCR fallback, batch jobs, deduplication | Normal/scanned/corrupt/duplicate inputs tested; errors visible | Next implementation increment |
| 4 | Login, role editor, candidate list, evidence panel, reviewer corrections and decision history | Recruiter completes a review; unauthorized access denied | Planned |
| 5 | Permitted URL imports, generic API/webhooks, first selected ATS connector | Auth, rate limits, retry and replay handling tested | Planned |
| 6 | Pilot, monitoring, retention/deletion, deployment | Recruiter-labeled evaluation meets agreed thresholds; access and recovery checks pass | Planned |

## Feature backlog

- Role criteria: explicit approval, immutable versions, required/preferred classification, acceptable evidence, clarification questions. Suggested criteria are drafts only.
- Input: paste, single/bulk file upload, permitted URL reading, signed webhook and scheduled sync. Each source produces the same input envelope.
- Extraction: responsibilities, projects, skills, employment intervals and relevant certifications with source references. Do not sum overlapping employment periods twice.
- Summary: relevant experience, supported strengths, ambiguous claims, missing evidence and interview questions. Each factual claim links to evidence.
- Assessment: meets, partial, not demonstrated, explicitly unmet. No unexplained suitability score. No sensitive characteristics or proxies as selection shortcuts.
- Review: interview recommendation, clarification, or non-advancement review. Reviewer sees evidence and records the actual decision separately.
- Operations: idempotency, bounded retries, failure queue, versioned prompts/models, cost and latency metrics, role-based access and tenant separation before multi-company use.
- Integration: connector health, least-privilege credentials, source provenance, external identifiers. ATS writes come later behind explicit reviewer action.

## Step 2 implementation tasks

1. Done: immutable role records and run records embedding candidate/source IDs and role snapshots in SQLite.
2. Done: pasted-text ingestion, 50,000-character limit, synthetic fixtures and request-id deduplication.
3. Done: provider interface, extractive demo and configurable OpenAI Responses adapter.
4. Done: schema-constrained facts, summary claims and criterion assessments; live calls still unverified.
5. Done: strict shape and source-excerpt validation before deterministic routing.
6. Done: authenticated loopback API and tests for success, failure, evidence, idempotency and untrusted-input separation. These tests do not establish live prompt-injection resistance.
7. Pending quality gate: configure a model/key outside GitHub and evaluate live results against recruiter-reviewed synthetic examples.

## Evaluation

Maintain synthetic regression fixtures and a separately controlled recruiter-labeled pilot dataset. Measure extraction correctness, unsupported claims, missed qualified candidates, agreement per criterion, review time, processing latency and cost. Agree numeric launch thresholds with the hiring team before the pilot. Evaluate outcomes across relevant groups only with an appropriate data-handling basis; never use those attributes for individual suitability decisions.

## GitHub workflow

Keep each increment small. Run unit tests for every change, add integration tests when an integration exists, and use branches/PRs for subsequent increments. CI contains no production credentials or candidate data. API keys and deployment secrets must be injected outside source control.
