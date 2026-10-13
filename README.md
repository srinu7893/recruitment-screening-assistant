# Recruitment Screening Assistant

A workflow-controlled recruitment assistant with planned LLM extraction and evaluation. Recruiters approve role criteria and make final hiring decisions.

## Current status

Foundation only: executable, dependency-free Python assessment validator and routing engine, synthetic example, tests, architecture and delivery plan. No live LLM, resume parser, web application, database, or external connector is implemented yet.

## Run locally

Requires Python 3.12 or newer. From the repository root:

```sh
python -m unittest discover -s tests -v
python -m screening examples/assessment.json
```

The CLI takes already structured assessments, checks evidence excerpts against source text, and outputs a review recommendation. It does not infer qualifications from raw resumes. An exact excerpt proves provenance, not that the interpretation is correct; a recruiter must review the evidence.

## Documentation

- [Delivery plan and feature backlog](docs/PLAN.md)
- [Architecture and data contracts](docs/ARCHITECTURE.md)

No candidate documents, production records, or credentials belong in this repository. Use synthetic fixtures. Integration support will be added connector by connector, subject to supported APIs and access.
