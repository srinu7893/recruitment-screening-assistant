# API and integration contract

One organization per instance. JSON endpoints require `Authorization: Bearer <token>` except the HMAC-authenticated webhook. Static dashboard assets contain no candidate data. Admin/reviewer/viewer identities come from configured server-side token mappings; clients cannot choose their acting reviewer.

All submissions and writes are rate limited. HTTP input is limited to 7.1 MB (allowing a base64-encoded 5 MB file). Profiles are limited to 50,000 characters, roles to 25 criteria, file PDFs to 20 pages. The local server accepts Host/Origin values for localhost or 127.0.0.1 on its port; it is not ready for an arbitrary public reverse proxy.

## Read endpoints

| Endpoint | Result |
| --- | --- |
| GET /health | Identity, provider and demo status |
| GET /roles | Approved role versions |
| GET /roles?version=… | Full role version |
| GET /runs | Summary rows and metrics; no full source texts |
| GET /runs?id=… | Full review record |
| GET /jobs | Last 100 job statuses |
| GET /interview?id=… | Criterion-based interview questions and evidence |
| GET /export?id=… | Full JSON review export; audited |
| GET /integrations | Configuration readiness, allowed hosts, last sync; no secrets |
| GET /audit | Latest 200 audit events, admin only |

## Write endpoints

Viewer accounts cannot write. Reviewers can ingest and review; admin-only routes are marked.

| Endpoint | JSON body |
| --- | --- |
| POST /roles (admin) | role_version, title, approved_by, criteria; acting approver overwritten from token identity |
| POST /roles/draft | description; line-based editable criteria draft, no automatic approval |
| POST /jobs or /screenings | request_id, role_version, profile_text |
| POST /uploads | request_id, role_version, filename, content_base64 |
| POST /imports/url | request_id, role_version, url |
| POST /imports/csv | role_version, csv |
| POST /integrations/sync (admin) | empty object |
| POST /rediscover | run_ids (1–20), role_version; creates fresh runs |
| POST /compare | run_ids (2–5); assessed runs of one role version |
| POST /preview | run_id, required_ids; read-only scenario calculation |
| POST /decisions | run_id, revision, decision (advance/reject/hold), reason |
| POST /notes | run_id, revision, text |
| POST /corrections | run_id, revision, reason, assessment (criterion_id/status/evidence) |
| POST /delete (admin) | run_id; deletes that run and associated job, rejects active processing |
| POST /retention (admin) | days (1–3650); removes eligible old runs |
| POST /jobs/cancel (admin) | id; queued or failed jobs only |

`/jobs` and `/screenings` now return **202 Accepted** with the job ID, not a synchronous result. Poll `/jobs`, then `/runs?id=…`. A completed job means processing finished; the run may still await human review. Failed jobs/runs never produce hiring decisions. Malformed input returns 400, unauthenticated 401, forbidden 403, missing 404, conflict 409, rate/queue busy 429. Partial batch imports include an `errors` array; inspect it before assuming all rows were accepted.

## Roles, evidence and decisions

See examples/role.json and examples/profile-request.json. Role versions are immutable. An assessment has a criterion_id, status (meets/partial/not_demonstrated/unmet), and evidence entries with source_id and exact quote. Substantive statuses require source-verifiable evidence. Missing criteria are normalized to not_demonstrated.

Every mutable reviewer operation uses `revision` from the latest run. A stale revision returns 409. Corrections preserve the original model result in `result`, put the effective assessment in `review_result`, update follow-ups, and reopen a previously decided run. Demo runs allow hold only; they cannot be advanced/rejected even after manual corrections.

## CSV and generic ATS feed

CSV columns: `external_id,profile_text`; quote fields containing commas or newlines. Up to 100 rows per batch. A source-specific external ID, role version and profile hash generate an idempotent job ID. CSV is an ATS-export adapter, not a claim that every platform exports the same schema.

A configured HTTPS JSON feed must return exactly:

```json
{"candidates":[{"external_id":"candidate-123","profile_text":"Built Python APIs…"}]}
```

Configure its fixed URL, optional bearer token, destination role and allowed hostname through environment variables. Up to 100 records per response; server-side pagination is not implemented, so the source must provide a bounded feed or webhook batches. Scheduled sync repeats the same idempotent import. Credentials are sent only to the configured URL. No ATS status or outreach writes are implemented.

## Signed webhook

POST `/webhooks/profiles` with body:

```json
{"role_version":"backend-engineer:v1","candidates":[{"external_id":"123","profile_text":"Built Python APIs…"}]}
```

Headers:

- `Content-Type: application/json`
- `X-Event-ID`: unique event identifier
- `X-Timestamp`: Unix seconds
- `X-Signature`: lowercase hex HMAC-SHA256 of `timestamp + "." + event_id + "." + exact_body_bytes`, keyed by SCREENING_WEBHOOK_SECRET

A valid timestamp must be within five minutes. Claims are atomic: concurrent replay attempts cannot both succeed. An accepted signature claims the event before ingestion; if payload validation fails, retry with a **new event ID**. Records remain independently idempotent. No external messages are sent.

## URL reading and document limits

Only exact allowlisted HTTPS hosts, port 443, public resolved IPs, verified TLS and no redirects. URL content types: plain text, HTML, PDF. HTML scripts/styles are discarded; login-protected or JavaScript-rendered pages are not supported. URL credentials/fragments are rejected. Only the source hostname is stored in metadata, avoiding persistence of signed query strings.

Files: 5 MB maximum; UTF-8 TXT; DOCX paragraphs/tables (no headers/footers/images/macros); 1–20 page PDF. Sparse PDF pages use English OCR. Parsing occurs in a resource-bounded Linux subprocess with a 120-second wall timeout; original files are deleted afterward. OCR results require review.

## Retry and recovery

Identical repeated request IDs return the existing job, including failure/cancellation. Different payloads with the same ID conflict. Use a fresh ID for an explicit retry. Queued jobs survive restart; interrupted work becomes failed and is never silently rebilled. Rediscovery reuses stored text with a fresh run ID and selected role. One server process per database is enforced.

## Showcase

`POST /showcase/load` with `{}` requires an admin token and a demo-mode workspace. Loads six original fictional profiles idempotently and returns `run_ids`, `role_version` and a notice. Authored fixture records remain marked demo and cannot advance or reject candidates. `/runs` metrics include `by_source` and `criteria_gaps` grouped by immutable role version and criterion.
