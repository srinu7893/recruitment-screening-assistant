# Recruitment Screening Assistant

A workflow-controlled recruitment assistant with an LLM adapter for extraction and evaluation. Recruiters approve role criteria and make final hiring decisions.

## Current status

Step 2: pasted-profile workflow, immutable approved role versions, SQLite persistence, evidence-backed facts and summaries, review routing, authenticated local JSON API, and an OpenAI Responses adapter. The offline demo works without credentials. Live-provider behavior is covered by mocked transport tests; an actual model call and quality evaluation are still outstanding.

This is a single-user development prototype. Uploads/OCR, browser dashboard, ATS connectors, real user accounts, production deployment and final-decision recording are not implemented yet.

## Run locally

Requires Python 3.12 or newer. From the repository root:

```sh
python -m unittest discover -s tests -v
python -m screening examples/assessment.json
python -m examples.demo
```

The original CLI validates prestructured assessments. The new demo exercises pasted-profile ingestion, persistence and summary validation. **Demo mode only copies profile excerpts and marks every criterion not demonstrated; it never evaluates qualifications.** Live mode uses the configured model. An exact excerpt proves provenance, not that the interpretation is correct; a recruiter must review the evidence.

## Local API quick start

In a Bash terminal, generate an access token and start demo mode:

```sh
export SCREENING_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m screening.server --provider demo
```

Use the same token in your API client. See [API usage](docs/API.md) for requests. The server binds only to `127.0.0.1`; it is not a production server or a browser dashboard.

For live mode, set `OPENAI_API_KEY` and `OPENAI_MODEL` securely in your environment, then run:

```sh
python -m screening.server --provider openai
```

Choose a model available to your account that supports Responses structured outputs. No model is silently selected. Live mode sends the supplied profile and role criteria to OpenAI; use synthetic examples until the workflow has been evaluated and your data handling approved. The adapter uses strict JSON-schema output, handles refusal/incomplete responses, and requests `store: false` ([official API guide](https://developers.openai.com/api/docs/guides/structured-outputs)). This setting is not a guarantee of zero provider retention.

## Documentation

- [Delivery plan and feature backlog](docs/PLAN.md)
- [Architecture and data contracts](docs/ARCHITECTURE.md)
- [Local API and limitations](docs/API.md)

No candidate documents, production records, or credentials belong in this repository. Use synthetic fixtures. Integration support will be added connector by connector, subject to supported APIs and access.
