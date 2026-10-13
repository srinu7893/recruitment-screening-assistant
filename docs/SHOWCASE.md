# Production-support showcase

## Present immediately, without accounts or API costs

Download `showcase/index.html` and open it in a browser. This self-contained page works offline: six original fictional resumes, authored summaries with exact source quotes, criterion assessments, evidence coverage, filters, a what-if preview, interview questions and TXT downloads. Click **Start 5-step walkthrough** for presenter prompts.

The authored fixture results are demonstration expectations, not live model outputs, validated model accuracy, or real candidates. Deterministic routing produces **2 interview recommendations, 3 clarification cases and 1 skill-gap review**. Human decisions remain separate.

## Demonstrate the working application

1. Follow the README local setup; start the server with `--provider demo` and sign in as admin.
2. Click **Load production-support showcase** in the pipeline. Repeating this action does not duplicate records.
3. Review **PS-101 Payments L2**: summary, evidence, required versus preferred skills, interview kit and what-if criteria.
4. Review **PS-103 Database support**: strong technical evidence but incomplete incident ownership. Ask the proposed clarification question.
5. Review **PS-106 Conflicting claims**: a skill-list assertion conflicts with the experience narrative. Inspect both quotes instead of accepting keywords.
6. Open **Insights** for criterion evidence gaps. Compare profiles within the same approved role version.
7. Add a note and record a **hold**. Demo records cannot advance or reject candidates, including after corrections.
8. Upload any supplied TXT sample to demonstrate the real ingestion and queue path. The generic demo provider only extracts text; live assessment requires a configured model.

CLI alternative: `python -m screening.showcase --db data/showcase.sqlite3`, then start the server against the same database in demo mode.

## Sample pack

`examples/production-support/` contains six original resumes and the approved role JSON. The canonical authored fixtures live in `screening/fixtures/production_support.json`. Rebuild the offline page with `python -m screening.build_showcase` after fixture or template changes. Backend tests validate every evidence quote and expected routing; browser tests cover filters, requirement changes, downloads and mobile layout.

A public production-support PDF was downloaded for extraction review. Its source link and a brief independent summary are in `examples/production-support/public-reference-summary.md`. The publisher's PDF is not redistributed in this repository.

## Still requires external setup

Live LLM quality evaluation, real ATS account mapping, recruiter pilot acceptance and production hosting/identity remain open. This demo proves the implemented workflow and authored scenarios; it does not close those gates. See PLAN.md for the full status table.
