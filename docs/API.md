# Local API: pasted-profile increment

Python 3.12+, standard library only. Start with the README commands. This is a synchronous, single-user development API, bound to loopback. Every endpoint requires `Authorization: Bearer <SCREENING_API_TOKEN>`. The token grants full access to all local records; this is not per-user authorization. Browser-origin requests are refused until a same-origin UI is added.

## Routes

| Method | Path | Meaning |
| --- | --- | --- |
| GET | /health | Health and provider name |
| POST | /roles | Create immutable approved role version |
| GET | /roles?version=backend-engineer%3Av1 | Fetch role version |
| POST | /screenings | Process pasted profile synchronously |
| GET | /runs?id=synthetic-demo-001 | Fetch persisted result or failure |

`POST /roles` takes examples/role.json. `approved_by` is the local operator's assertion of approval, not a verified user identity. New criteria require a new role_version. Requirements must be approved, job-related and exclude sensitive attributes; automated policy enforcement of free-text criteria is not implemented.

`POST /screenings` takes examples/profile-request.json. A profile is limited to 50,000 characters; HTTP bodies to 250,000 bytes. Profile text, role data and outputs persist locally in `data/screening.sqlite3` (ignored by Git). The default new data directory/file are private to the OS account, but SQLite data is not encrypted at rest by this app.

## Example requests

Run these from the repository root in a shell with the same SCREENING_API_TOKEN as the running server:

```sh
curl --fail-with-body http://127.0.0.1:8000/roles \
  -H "Authorization: Bearer $SCREENING_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/role.json

curl --fail-with-body http://127.0.0.1:8000/screenings \
  -H "Authorization: Bearer $SCREENING_API_TOKEN" \
  -H 'Content-Type: application/json' \
  --data-binary @examples/profile-request.json

curl --fail-with-body 'http://127.0.0.1:8000/runs?id=synthetic-demo-001' \
  -H "Authorization: Bearer $SCREENING_API_TOKEN"
```

A successful processing record has `status: awaiting_review`, a `result` containing facts, summary claims, criterion assessments, recommendation, and follow-up questions. `human_review_required` is always true. Source excerpts and role snapshot remain in the run for review. Treat every returned text string as untrusted if building a UI; render it as text, never raw HTML.

## Failures and repeated requests

- Malformed requests: HTTP 400. Missing token: 401. Unsupported browser origin: 403. Missing role/run: 404. Conflicting role version or request ID: 409. Body limit: 413. Wrong media type: 415.
- Accepted screening requests return HTTP 200 with the persisted run. Callers must inspect `status`; processing failures have `status: failed`, an error code and `result: null`.
- Identical repeated request IDs return the existing run without another provider call, including failed/in-progress runs. Changing input or provider requires a new request ID.
- No automatic retry: this avoids repeated billing and hidden result changes. Retry a failed call using a new request ID after fixing the issue.
- A process crash can leave received/evaluating/validating records. They remain visible; after confirming the old process is stopped, rerun with a new request ID. Durable worker recovery is planned.
- Do not run multiple API server processes against this prototype. Repeated requests within one server are safely deduplicated in SQLite.

## Live provider

The adapter uses the fixed HTTPS OpenAI Responses endpoint, rejects redirects, applies a 45-second socket timeout, limits response size, supplies no tools and validates model output locally. Provider refusals, incomplete responses, invalid JSON, rate limits and connection errors create failed runs. HTTP bodies and API keys are not logged or saved. `OPENAI_MODEL` is required explicitly; verify Responses/structured-output support for the chosen model.

Evidence validation confirms exact quote provenance only. A model can attach an irrelevant excerpt to an incorrect interpretation, and that requires semantic evaluation and human review. Prompt separation and strict contracts reduce the impact of injected profile instructions; the tests do not prove that a live model cannot be manipulated.

## Production gates still outstanding

Live model evaluation; real authentication/authorization; job-related criteria validation; retention/deletion controls; encryption deployment; request rate limiting; worker recovery; upload processing; multi-tenant isolation. Do not expose this development server publicly or use it for unattended hiring decisions.
