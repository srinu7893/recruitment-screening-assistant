# Architecture and contracts

## Target system

Upload, paste, URL and ATS adapters normalize input into SourceDocument records. A persisted workflow extracts text, calls a bounded model adapter, validates facts and assessments, then opens a recruiter review. Proposed later components: Python API/worker, PostgreSQL metadata, private object storage, and a web dashboard. These components are not installed in this foundation.

Workflow states: received, extracting, evaluating, validating, awaiting_review, completed, failed. Failures never become hiring rejections. Persist state transitions and retry count. Deduplicate within a tenant/source scope using an external event ID or document hash; never merge people solely by name.

## Target records

| Record | Essential fields |
| --- | --- |
| RoleVersion | role_id, version, description, criteria, approval actor/time |
| SourceDocument | source_id, kind, external_id, hash, private object key, extracted text, page/offset map |
| CandidateProfile | candidate_id, supported facts and evidence references |
| ScreeningRun | run_id, candidate_id, role_version, source versions, model/prompt version, status |
| Assessment | criterion_id, status, source references, rationale |
| ReviewDecision | run_id, reviewer, decision, reason, timestamp |

## Executable foundation input

See examples/assessment.json. Required fields are role_version (nonempty string), criteria (nonempty list of unique id/required objects), sources (source ID to text mapping), and assessments (unique criterion_id/status objects with optional evidence). Each evidence item has source_id and an exact quote. Supported statuses: meets, partial, not_demonstrated, unmet. The latter means explicit contrary evidence, not silence. This foundation accepts pre-assessed evidence, not untrusted model output directly from a production API.

The core validates all supplied assessments, rejects unknown or repeated criterion IDs, and requires verified excerpts for every status other than not_demonstrated. Missing assessments are normalized to not_demonstrated. Any unresolved required criterion leads to needs_clarification; explicit unmet required criteria lead to review_non_advancement; all required criteria met leads to recommend_interview. Roles with no required criteria always go to needs_clarification. Preferred criteria appear in output but do not block an interview recommendation. Every output requires human review; no final hiring decision is emitted.

## Boundaries

- Excerpt matching checks traceability only. It cannot prove entailment, detect contradictions, or validate the candidate's real-world claims. Future semantic checks and recruiter review address these separately.
- Treat document text as data, never as system instructions. Models receive no execution tools or hiring-system write credentials.
- Approve only job-relevant criteria. Remove sensitive personal attributes from model evaluation inputs where feasible; the current core is not a demographic filter.
- Uploads require type/size checks, isolated parsing, malware controls and document retention rules before production.
- URL imports require supported-source policy, redirect/IP validation and outbound restrictions to prevent SSRF; do not fetch arbitrary internal URLs.
- Use scoped secrets, authorization per object, encrypted storage, and logs without raw profiles. CI tests use synthetic data only.
- Webhooks require signature verification and replay protection. Retry transient errors with bounded backoff; permanent errors need visible remediation.

## Testing boundaries

Current tests cover deterministic routing and malformed evidence contracts. Live extraction, summary quality, prompt injection resistance, OCR, connectors, access control and deployment are later acceptance gates, not claims of current functionality.
