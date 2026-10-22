# Manager demonstration kit

Start with [PROCESS.md](PROCESS.md) for the five-step walkthrough. The reviewed
feature priorities are in [../PLAN.md](../PLAN.md); specific findings and scope
are in [../PRODUCT_REVIEW.md](../PRODUCT_REVIEW.md).

The application is suitable for a presenter-led demonstration of its verified
workflow. It is a literal evidence assistant, with human review; do not present
it as semantic qualification assessment, automated ranking or autonomous hiring.

## Shareable artifacts

- `presentation.html`: standalone 12-page HTML presentation. Open in a browser;
  use **Present** and the arrow keys, or **Print / PDF**. It includes TXT resume
  downloads and needs no network connection except to open the live app link.
- Run `python -m scripts.build_manager_demo` after installing development
  dependencies to create PDF and TXT resumes in `artifacts/manager-demo/`.
- `screening/fixtures/manager_demo.json`: reproducible role and fictional source
  profiles. Every profile is explicitly labelled fictional.

The presentation covers business needs, value hypotheses, implementation,
architecture, workflow automation, evidence rules, validation, limitations,
remaining work and an eight-minute walkthrough. Metrics are proposed pilot
measures, not claimed ROI or proven screening accuracy.

## Add five fictional resumes to the live workspace

Run in your existing authenticated Cloud Shell checkout:

```bash
cd ~/recruitment-production
git pull --ff-only origin main
.cloud-setup-venv/bin/python -m scripts.seed_manager_demo
```

Enter `admin` and your application password privately. The command uses the
normal HTTPS login and upload APIs; the deployed scanner and background worker
process every file. It verifies results, adds clearly labelled demonstration
notes and signs out. It never reads database credentials or changes real
records. No application deployment is needed for this client-side loader.

Stable role/job IDs make repeats reuse the same jobs. Existing edited notes or
decisions are retained. A role with conflicting criteria or a previously deleted
or cancelled demonstration job requires manual inspection; the loader does not
silently replace it. A failure can leave some fictional records already loaded.

Filter the pipeline by **DEMO ONLY - Production Support Engineer L2**
(`manager-demo-support:v1`). Expected criteria with mentions:

| Profile | Scenario | Mentions / 5 |
| --- | --- | --- |
| DEMO-101 | Broad mentions | 5 |
| DEMO-102 | Core support mentions; preferred gaps | 3 |
| DEMO-103 | Adjacent development evidence | 2 |
| DEMO-104 | No literal evidence for the role | 0 |
| DEMO-105 | Negated mentions requiring interpretation | 2 |

All initial recommendations are **Clarification needed**. Even a matched phrase
is partial evidence. The negation example intentionally shows that a term match
is not demonstrated competence. Correct assessments only with a stated reason
and source evidence. Use fictional notes and a hold decision in the walkthrough.

## Showing the agent

The uploaded resumes automatically move through queued / processing / completed
jobs to saved evidence reviews. Show **Automation → All processing jobs** to
explain this worker. Upload one of the supplied PDFs during the meeting to show
the transition live, then open its saved review.

The scheduled intake agent is implemented and tested, but the supplied production
configuration has no live source feed. Do not enable or claim live source polling
until an approved feed/connector is configured and verified. Local folder
watching is supported in local installations, not Cloud Run.

## Readiness

Ready for the manager demo: deployed login, database-backed workflow, uploads,
scanning, background evidence matching, review records and audit.

Before a wider team pilot: individual accounts, access lifecycle, password
recovery, agreed retention, backup/restore exercise, monitoring/alerts, load and
failure testing, recruiter calibration and consented input handling. Connect a
real source only when its credentials and operating process are available.

Keep the admin password private; present from your own signed-in browser. Give
other users separate accounts for independent access. No real applicants are
required to demonstrate this pack. Retire fictional records after the demo if
they are no longer needed, using the normal record deletion control.
