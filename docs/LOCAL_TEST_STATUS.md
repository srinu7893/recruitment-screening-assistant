# Local implementation and validation — 16 October 2026

The application has one Python server serving both the dashboard and API, plus a background screening worker. The offline showcase is a separate static website. There is no separate frontend build server.

## Running locally

- Full application: **http://127.0.0.1:8000**, using a persistent local SQLite database. The dashboard, API, screening queue and intake scheduler run together. Sign in with the token in ignored file `data/local-token.txt` and restart with `start-local.cmd`.
- Native Windows startup and document extraction now work, using Windows ownership locks and parser Job Object limits. Linux protections remain in place. Docker/WSL is no longer needed for local workflow testing.
- The launcher creates six labeled fictional profiles and one incoming synthetic resume. Automation settings are retained after restart. See `APPLICATION_DEMO.md`.

Python 3.12 was found outside PATH; `.venv` contains the pinned development dependencies. Node dependencies and Playwright Chromium are installed.

## Checks executed

| Area | Result |
| --- | --- |
| Offline six-profile rendering | Passed in Chromium |
| Guided tour | Passed |
| Scenario filters | Passed |
| Requirement-change preview | Passed |
| Sample resume download | Passed |
| Mobile overflow and browser errors | Passed |
| Backend suite including real PostgreSQL | **126 tests: 124 passed, 2 skipped** |
| Digital PDF, DOCX and UTF-8 TXT | Passed on native Windows |
| Full app startup | Passed; persistent workspace running on port 8000 |
| Full app browser workflow | Passed: login, roles, paste/upload, screening, notes, decisions, scorecards, assignments, comparison, analytics and mobile views |
| Automatic intake browser workflow | Passed: manual/scheduled intake, failures/retries, restart persistence/deduplication, review links and mobile layout |
| PostgreSQL persistence and migration | Passed, including schema isolation, independent schema workers, handoff, fencing, interrupted-job recovery and automation settings/history |
| Cloud release validation | Passed identity, image/secret pinning, feed configuration and traffic-preservation contracts |

The two skips are scanned-PDF OCR and a real ClamAV daemon; system dependencies are not installed locally. The isolated recruitment PostgreSQL test cluster uses loopback port 55433, a dedicated `screening_test` database and files under this repository. The payment database was not changed. Backend logs and screenshots are in ignored `test-results/`.

Repeat browser checks with `npm run test:ui`, `npm run test:automation` or `npm run test:showcase`; set `PYTHON` to this project's `.venv\Scripts\python.exe` first for the first two. Run `.venv\Scripts\python.exe scripts\test_local.py --postgres-url-file data\test-postgres-url.txt` while the dedicated PostgreSQL service is running; omit the flag to skip PostgreSQL. Run `scripts\summarize_local_tests.py` with the same Python to summarize the saved log.

## Built scope

Code and tests cover approved immutable role versions, pasted/document/CSV intake, background screening, evidence review, notes/corrections/decisions, scorecards, assignments, comparisons, requirement previews, rediscovery, analytics, audit/export/retention/backup, scoped access, generic webhooks/feed imports, Greenhouse, IAP, PostgreSQL and cloud deployment. Added persistent Automation controls, a watched local resume inbox, intake receipts, deduplication, explicit retries and processing/review links. Deleted inbox records are redacted and leave deduplication tombstones so retained originals do not recreate them.

Fixed Windows startup/parser limits, mobile overflow, rejected-request connection resets, UTF-8 file errors and misleading processing-stage labels. Cloud config now wires feed allowlists/URLs, intervals, roles and retention. Implementation does not establish live external-system acceptance.

## Remaining work in order

1. Complete `CLOUD_SETUP_CHECKLIST.md`, using discovered project `project-c9bd3d0e-266f-47bf-852` and region `us-central1`. The project-specific draft is `deploy/cloud-run/config.discovered.example.json`.
2. Confirm billing, project number, canonical service URL, dedicated database/secrets, IAP users/OAuth and GitHub WIF access for this repository. No cloud deployment was performed.
3. Configure a chosen live model/key and a real source/ATS mapping, then validate their credentials and recruiter-labeled quality thresholds.
4. Run Linux/container CI and the authenticated cloud upload/restart smoke tests, including real scanner and OCR operation. Verify backup restore and retention.
5. Complete the recruiter pilot and production security review. Laptop inbox watching is local-only; Cloud Run uses browser uploads and configured sources.

Multilingual OCR, high-volume ingestion and tenant isolation remain future scope. See `PLAN.md` and `ADVANCED_WORKFLOWS.md` for detailed external acceptance gates. Demo mode is suitable for workflow testing and permits hold decisions only.
