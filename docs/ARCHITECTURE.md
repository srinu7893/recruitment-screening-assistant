# Architecture

## Running system

A Python HTTP service serves the static recruiter dashboard and authenticated API. SQLite persists roles, runs, background jobs, audit events and webhook replay claims. One background worker processes queued profiles; a separate optional maintenance thread handles scheduled feed sync and retention.

Inputs pass through normalization into the same profile-text contract. Documents are parsed in a bounded child process; originals live only in a temporary directory. OpenAI mode uses a schema-constrained Responses call with no tools, no profile URLs fetched by the model, a fixed HTTPS endpoint, socket timeout and bounded response. Demo mode is extractive and produces no suitability judgments.

All model output passes local shape and exact-source-excerpt validation before deterministic routing. A reviewer sees the evidence and records the hiring decision separately. Free-text claims can still be semantically wrong despite matching an excerpt; this remains an evaluation/review responsibility.

## Records

| Record | Stored information |
| --- | --- |
| Role version | Title, approved criteria, reviewer identity, approval timestamp; immutable |
| Screening run | Candidate alias, source text/hash/provenance, role snapshot, model/prompt identity, states, results, errors, decisions/notes/corrections |
| Job | Request, origin and status while queued; profile payload removed after processing/cancellation |
| Audit | Actor, action, target and timestamp; no profile body |
| Webhook event | Event identifier and timestamp for replay rejection |

Candidate IDs are per run. Rediscovery records the parent run rather than claiming authoritative identity resolution. Duplicate notices compare exact extracted-text hashes; they never merge people by name.

## States and concurrency

Queued → processing → completed/failed/cancelled at the job layer. Runs move received → evaluating → validating → awaiting_review, or failed. A human advance/reject decision marks a run completed; hold leaves it awaiting review. Evidence corrections reopen review, preserve the original model result and invalidate the active decision with a recorded hold.

SQLite transactions enforce immutable roles, unique request IDs, atomic webhook claims and revision-based human edits. One server process owns a database lock. After restart, interrupted runs/jobs are marked failed; they are not silently repeated, avoiding unobserved model charges. Retry/reassessment creates a new request ID. Queued unstarted jobs survive restart. A provider/model change prevents old queued jobs from silently using a different configuration.

## Trust boundaries

- Admin, reviewer and viewer tokens grant different operations within one organization. There is no tenant isolation or SSO.
- The dashboard uses same-origin requests and text-node rendering; tokens stay in memory. CSP blocks inline scripts and framing.
- URL ingestion requires configured exact hosts, HTTPS, public resolved addresses and a connection pinned to the validated IP with TLS host verification. Redirects are refused. Feed credentials are sent only to the configured feed URL.
- Signed webhooks bind timestamp, event ID and exact body; events outside five minutes or replayed IDs are rejected.
- Upload checks enforce extensions, signatures, size, archive expansion, page count, time/CPU/memory and no macro/entity execution. The parser process is resource-bounded, not a complete security sandbox; production malware scanning is still a deployment gate.
- Saved SQLite data is private to the OS account but is not encrypted by this application. Configure encrypted disks/backups for production.
- No automated emails, outreach, ATS status updates or final model hiring decisions.

## External API reference

The OpenAI adapter follows [official Structured Outputs guidance](https://developers.openai.com/api/docs/guides/structured-outputs) with strict schema output and handling for refusal/incomplete results. `store: false` is requested; it is not a promise of zero provider retention. The configured model must support the request format.
