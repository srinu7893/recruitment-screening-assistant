# Shortlist — Recruitment Screening Assistant

A recruiter workspace for evidence-backed profile summaries, role-based screening and human decisions. The workflow controls ingestion, validation and routing; an optional LLM interprets job-related evidence.

## Show it to your manager

Open [showcase/index.html](showcase/index.html) locally for an interactive offline production-support dashboard. It includes six fictional resumes, authored summaries, evidence, coverage charts, filters, interview questions and requirement-change previews. No API key is needed. Follow the [five-minute showcase guide](docs/SHOWCASE.md).

In the running demo application, admins can click **Load production-support showcase**. These curated records are clearly labeled and support hold decisions only.

## Cloud deployment and persistent data

The full app needs a Python/container host; GitHub Pages supports only the offline showcase. [Neon deployment guide](docs/NEON_DEPLOYMENT.md) covers PostgreSQL, verified TLS, public HTTPS configuration, health checks and migration from SQLite. Use `compose.neon.yaml` on a single container host with a stop-before-start deployment. Standard Cloud Run rolling deployment remains a separate worker-architecture task.

Reviewer assignments now include priority, due dates, assigned-to-me/overdue filters and team workload analytics. These organize review work without changing candidate assessments.

## What you can use

- Role creation with editable job-description drafts, required/preferred criteria, approval identity and immutable versions.
- Pasted profiles, batch PDF/DOCX/TXT uploads, scanned-PDF English OCR, CSV imports and allowlisted public HTTPS sources.
- Durable background screening, explicit demo mode, OpenAI Responses adapter, evidence-backed summaries and criterion assessments.
- Responsive recruiter dashboard: queue, filters, review panels, source excerpts, decisions, notes and evidence corrections.
- Criterion comparison, interview guides, role-change previews and reassessment of saved profiles for new roles.
- Signed webhooks, generic ATS exports and a configured JSON feed with optional scheduled synchronization.
- Admin/reviewer/viewer tokens, audit events, duplicate-text notices, retention/deletion, JSON export and verified backups.

**Demo mode does not assess qualifications.** It copies excerpts, marks criteria not demonstrated, and allows hold decisions only. Live mode requires your configured model and API key. All hiring decisions remain with reviewers.

## Start locally (Linux / Python 3.12+)

```sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Ubuntu/Debian: required for scanned PDF OCR
sudo apt-get install poppler-utils tesseract-ocr fonts-dejavu-core
export SCREENING_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python -m screening.server --provider demo
```

Open **http://127.0.0.1:8000** and enter the token from your environment. Create a role in **Roles & criteria**, add synthetic profiles, and review them in **Review pipeline**. Tokens stay in browser memory and are cleared on refresh/sign-out. Originals are discarded after extraction; extracted profile text persists in the private data directory.

For a quick terminal demo without installing document dependencies:

```sh
python -m examples.demo
```

For live evaluation, set `OPENAI_API_KEY` and `OPENAI_MODEL` securely in the server environment, then run `python -m screening.server --provider openai`. Use a model that supports Responses structured outputs. No model is silently selected. Never paste API keys into GitHub or candidate text.

## Run in Docker

```sh
export SCREENING_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
docker compose up --build
```

The Compose service defaults to demo mode and exposes port 8000 on loopback only. Set `SCREENING_PROVIDER=openai` plus the model/key for live mode. See [deployment and operations](docs/DEPLOYMENT.md).

## Test

```sh
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
npm install
npx playwright install chromium
npm run test:ui
```

CI runs backend/document tests, real-browser acceptance and a container build. Synthetic inputs only. Test screenshots are downloadable from the Actions run; they are not committed as candidate artifacts.

## Documentation

- [Phase status and remaining acceptance gates](docs/PLAN.md)
- [Features and market-informed additions](docs/FEATURES.md)
- [Architecture](docs/ARCHITECTURE.md)
- [API and integration contract](docs/API.md)
- [Deployment, accounts, backup and retention](docs/DEPLOYMENT.md)
- [Validation and known limitations](docs/VALIDATION.md)

## Scope and current limits

This is a local, single-organization MVP, not a certified production hiring system. A quote match validates provenance, not whether an interpretation is correct. Live-model quality evaluation and real ATS-account verification remain external acceptance gates. The generic feed/webhook contracts need mapping for each ATS; arbitrary platforms are not automatically supported. SSO, tenant isolation, production TLS, encrypted storage deployment and independent security review remain production work. No external messages or ATS hiring-state changes are sent.
