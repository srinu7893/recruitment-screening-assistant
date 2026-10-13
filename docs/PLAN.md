# Delivery plan

## Product goal

Give recruiters consistent summaries and evidence-based comparisons against approved job requirements. Automate ingestion and processing; retain human responsibility for advancement and rejection. Missing information is not a failed requirement.

## Architecture decision

Use a controlled workflow with bounded LLM steps. The workflow owns status, retries, validation and routing. The model extracts and evaluates context against a fixed criteria version; it cannot alter criteria, execute instructions inside resumes, send messages, or change ATS hiring status. Start with one service and a worker before considering multiple autonomous agents.

## Milestones and acceptance gates

| Phase | Features | Acceptance gate | Status |
| --- | --- | --- | --- |
| 1 | Plan, architecture, structured assessment core, synthetic example, CI | Local tests and sample CLI pass | Implemented in foundation |
| 2 | Approved role configuration, pasted profile, LLM adapter, grounded summaries and assessments | End-to-end profile-to-review on synthetic samples; invalid model output fails safely | Next |
| 3 | PDF/DOCX uploads, file limits, scan/OCR fallback, batch jobs, deduplication | Normal/scanned/corrupt/duplicate inputs tested; errors visible | Planned |
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

1. Add durable role, source, candidate and run records with approved criteria versions.
2. Implement pasted-text ingestion with input limits and synthetic fixtures.
3. Define an LLM provider interface plus deterministic fake for tests; choose provider/model before live wiring.
4. Implement schema-constrained extraction and evidence-backed summary generation.
5. Validate every model output before calling the existing routing engine.
6. Add a minimal API and end-to-end tests for success, missing evidence, malformed output, timeout and prompt injection attempts.

## Evaluation

Maintain synthetic regression fixtures and a separately controlled recruiter-labeled pilot dataset. Measure extraction correctness, unsupported claims, missed qualified candidates, agreement per criterion, review time, processing latency and cost. Agree numeric launch thresholds with the hiring team before the pilot. Evaluate outcomes across relevant groups only with an appropriate data-handling basis; never use those attributes for individual suitability decisions.

## GitHub workflow

Keep each increment small. Run unit tests for every change, add integration tests when an integration exists, and use branches/PRs for subsequent increments. CI contains no production credentials or candidate data. API keys and deployment secrets must be injected outside source control.
