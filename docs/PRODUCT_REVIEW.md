# Product review — 22 October 2026

Update, 23 October: the phrase editor, source availability, account/recovery and
retry gaps described below are addressed in the team-workflow release code.
Deployment and external source/alert verification remain separate steps. See
[TEAM_WORKFLOWS.md](TEAM_WORKFLOWS.md) and the release table in [PLAN.md](PLAN.md).
The findings below are retained as the review that motivated this implementation.

## Conclusion

The application supports a manager demonstration of resume intake, background
processing, evidence review and record tracking. The current rules mode is not
automatic qualification assessment or ranking. The most useful next work is
easier setup and operation, rather than more pages.

## Confirmed findings

### 1. Role setup can silently produce no matches — priority 1

`screening/rules.py` reads phrases inside straight double quotes.
`screening/contracts.py` validates role structure but does not require matching
phrases. The job-description draft splits text into criteria without adding
quotes. An ordinary valid requirement can therefore produce only
`not_demonstrated` results even when the relevant words appear in the resume.

Next development: separate matching-phrase inputs from the requirement, show a
preview, and warn before saving a criterion with no phrases. Keep old versions
intact. For the current demo, use the supplied quoted criteria.

### 2. Automation does not make source availability clear — priority 1

The screen includes a local inbox checkbox and folder instructions. Cloud Run
disables local folder intake. `Automation.update` rejects unavailable sources,
but only after the user tries to save an enabled configuration.

Next development: show availability before configuration. Keep processing jobs
visible when no intake source is connected. Uploads already enter the background
worker without enabling scheduled source intake.

### 3. Team accounts need operator work — priority 1

Roles and password verification exist. The helper writes a complete account
list to Secret Manager. There is no account-management screen, self-service
recovery or invitation flow. Replacing the single-admin secret is not a team-user
management process.

Next development: auditable account create/disable/reset and individual access.
Use the presenter's session for the demo. Individual accounts can currently be
provisioned through configuration.

### 4. Retry behavior is spread across screens — priority 2

Inbox import failures have an explicit retry. Failed runs can be submitted again
as new runs. There is no consistent retry action for every failed queue job,
especially when processing fails before a review record is saved.

Next development: a processing-state view with a readable error, a retry action
and links between the original and retried job. Do not silently repeat work.

### 5. A real source is not connected — configure, then verify

The production setup does not specify a feed URL, source credentials or
Greenhouse access. Generic adapters and local/mock tests do not prove a working
live integration. Configure one approved source and demonstrate a scheduled
import before claiming unattended source collection.

### 6. Readiness documentation was stale — corrected

The old plan listed cloud provisioning, Neon access and clean upload scanning
as pending after publication passed those checks. It also mixed optional IAP
and model validation with the current password/rules deployment. `PLAN.md` now
separates deployed behavior, tested code, unconfigured connections and remaining
development or operating checks.

## Known engine limits

- `No hands-on Docker experience` still produces a literal mention. Read context.
- Different wording is not treated as equivalent. Duration and proficiency are
  not calculated.
- All untouched manager-demo profiles route to clarification. Evidence coverage
  counts mentions; it is not a suitability score.
- Uploaded files are discarded after extraction. Text and review records persist.
  Original-file storage would be separate development.

## Scope

This was a source, workflow and documentation review using the reported live
publication result and existing CI coverage. It did not sign into production,
confirm that the five demo profiles were loaded, perform a new load test, or
verify a real ATS connection. All supplied manager profiles remain fictional.
