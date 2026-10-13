# Validation ledger

## Executed locally

- Python unit/integration suite: routing, evidence contracts, profile workflow, queue, token authentication, HTTP round trip, decisions, corrections, revisions, retention, CSV import and backups.
- Actual document parsers: digital PDF, DOCX body/table, TXT and image-only PDF OCR.
- Concurrent idempotency and webhook replay-claim tests.
- Source URL validation: disallowed schemes/hosts, private/metadata IPs, public-address pinning contract.
- Mocked provider/feed transport: success, refusal, incomplete/malformed JSON, timeout, HTTP error, feed mapping.
- JavaScript syntax checks and offline demo.

## CI gates

- Repeat the Python/document suite with OCR dependencies installed.
- Real Chromium acceptance: login, role approval, paste/upload, background completion, review decision, notes, evidence comparison, safe rendering and desktop/mobile screenshots.
- Build the Docker image.

See GitHub Actions for actual per-commit results. A workflow file alone does not prove the gate passed.

## Not validated with external systems

- No real model/API-key call or model quality benchmark.
- No live ATS account or webhook delivery from a named platform.
- No public production deployment, SSO/tenant audit or independent security assessment.
- No claim of immunity to prompt injection, demographic bias, fraud, or unsupported semantic interpretations.

## Pilot protocol

Prepare synthetic and appropriately controlled recruiter-labeled profiles for one real role. Include missing evidence, equivalent terminology, conflicting claims, overlapping jobs, scanned pages, malformed documents and injected instructions. Agree expected criterion statuses before looking at model output. Measure unsupported claims, missed qualified profiles, criterion agreement, review time, latency and actual provider cost. Set launch thresholds with the hiring team. Do not tune against historical accept/reject labels without examining their quality and bias.

Final hiring decisions require human review. Exact quotes establish provenance only; a quoted phrase may still fail to support a model's conclusion.
