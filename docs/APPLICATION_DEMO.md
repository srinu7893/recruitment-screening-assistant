# Full application walkthrough

## Start and enter

Run `start-local.cmd` from this repository on Windows, or `.venv\Scripts\python.exe -m screening.local --showcase`. If the app is already running, open http://127.0.0.1:8000. Read the workspace token from `data/local-token.txt` and paste it into the login form. No token is embedded in the web page or committed to Git.

This starts the dashboard, API, background screening worker and intake scheduler together. It creates six clearly labeled fictional examples, one synthetic incoming TXT resume and an approved role. On first setup, local inbox automation is enabled. Later changes to settings survive restart and are not overwritten by the launcher. Use `python -m screening.local` without `--showcase` to start without creating fictional records.

## Show the automatic workflow

1. Open **Command center** to inspect review stages, evidence coverage, source channels and runtime health.
2. Open **Automation**. Confirm the approved role, enabled inbox source and check interval. Its folder is `data/inbox` by default.
3. Copy a synthetic PDF, DOCX or UTF-8 TXT resume into that folder. The running agent checks every 60 seconds by default. **Check sources now** triggers a cycle immediately; files must have finished writing at least two seconds earlier.
4. Watch **Intake records** and **All processing jobs**. The agent extracts text, queues screening and prepares a linked review record. Repeating a check or restarting does not create a second job for the same file content/name/role.
5. Open the review. Inspect the source excerpt, summary, criteria and questions. Add a reviewer note, assignment and due date; record interview observations and a hold decision. Every edit is attributed and audit history is available in Insights.
6. Compare selected profiles, preview changed criteria, or reassess saved text against another approved role. Export a review JSON to inspect its stored record.
7. Restart the application and confirm profiles, notes, decisions, assignments and automation settings remain.

Direct uploads in **Add profiles** use the same background queue without requiring a scheduled cycle. CSV and configured source imports are also tracked in the processing ledger. Upload batches support up to 20 files; the inbox processes up to 20 new files each cycle.

## Failures and record controls

Invalid or blocked documents appear as failed intake records. Fix/replace the file, or use **Retry import** after resolving a temporary scanner problem. A retry is explicit and audited. Queue capacity/parser contention is retried on a later cycle rather than permanently marking the file imported. Interrupted live model calls are not silently retried, avoiding unintended repeat charges.

Deleting a saved inbox review removes its text and job and redacts its receipt. A deduplication tombstone prevents the retained file from recreating that deleted record. Inbox originals remain on your filesystem; remove those separately according to your retention policy. Uploaded originals are discarded after extraction.

## Demo and live operation

The local showcase uses demo mode. Uploaded or inbox resumes are copied into evidence excerpts and prepared for review; qualifications are not evaluated. The six curated examples have authored, validated summaries and remain labeled. Demo decisions are hold-only.

For real model-backed screening, configure `OPENAI_API_KEY` and your selected `OPENAI_MODEL` securely and start `python -m screening.server --provider openai` with a strong workspace token, or use the protected Cloud Run release described in `CLOUD_SETUP_CHECKLIST.md`. Use a separate database/service for demo and real records. Live hiring decisions still require a reviewer.

Scanned-PDF English OCR requires Poppler and Tesseract, which are included in the Linux container. Digital PDF, DOCX and TXT parsing works natively on Windows. Local development explicitly reports when malware scanning is disabled; Cloud Run uploads require the scanner sidecar and fresh signatures.
