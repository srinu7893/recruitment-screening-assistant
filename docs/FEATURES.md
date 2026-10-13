# Product features and rationale

## Market-informed additions

Reviewed official product pages on 2026-10-13:

- [Ashby — AI Talent Rediscovery, released May 7, 2026](https://www.ashbyhq.com/product-updates/ai-talent-rediscovery): demonstrates reassessing existing candidate pools against a role's criteria. Our MVP reuses saved profile text and creates a fresh, traceable assessment for the selected role. It does not refresh external profiles or infer candidate intent.
- [Greenhouse — Real Talent](https://www.greenhouse.com/real-talent-candidate-matching): describes candidate matching with transparent explanations and recruiter control. Our MVP exposes criterion evidence and a separate human review record. It does not claim identity verification or fraud detection.

These are examples of current product directions, not a market-prevalence study or proof of the vendors' effectiveness.

## Additional features in this MVP

| Feature | User benefit | Boundary |
| --- | --- | --- |
| Evidence coverage | Shows how many criteria have supporting excerpts | Not a candidate-quality score |
| What-if preview | Lets a hiring manager test required/preferred choices | Never changes the approved role or past decision |
| Criterion comparison | Makes evidence comparable across 2–5 profiles | Same role version only; no opaque ranking |
| Interview kit | Turns criteria into concrete follow-up questions | Recruiter-authored questions, not an automatic interview |
| Talent rediscovery | Reassesses up to 20 saved profiles for another role | Creates new runs; does not silently replace earlier assessments |
| Duplicate-text notices | Highlights repeated content for review | Does not merge identities or label candidates fraudulent |
| Evidence corrections | Lets reviewers fix extraction/evaluation mistakes | Requires evidence, reason, revision and audit history |
| Demo guard | Prevents placeholder inference from looking like real screening | Demo permits hold only, even after corrections |
| Private team notes | Preserves recruiter context for later review | Notes never become automatic future selection criteria |
| Retention and deletion | Limits unnecessary retention of candidate records | Backups and separate imported copies need their own lifecycle |

## Input support

Paste; TXT; digital PDF; scanned English PDF; DOCX body paragraphs/tables; CSV with profile text; allowlisted public PDF/HTML/text URLs; signed custom webhooks; fixed JSON feeds. Each path reaches the same screening and review workflow. Exact format limits and contracts are in API.md.
