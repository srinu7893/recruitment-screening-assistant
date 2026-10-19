# Production login and no-API screening

The `rules` provider runs locally without a model API or API billing. Recruiters
put exact phrases in double quotes in approved criteria, for example
`Experience building "Python" services with "PostgreSQL"`. Matching source lines
appear as **partial evidence requiring review**. Missing text is not a failure;
the engine does not infer duration, proficiency, equivalence or suitability.
Reviewers can correct assessments with evidence and record decisions. This is
literal evidence assistance, not semantic AI evaluation or automatic hiring.

Password mode uses PBKDF2-SHA256 password hashes, database-backed eight-hour
sessions, Secure/HttpOnly/SameSite cookies in HTTPS deployments, CSRF tokens,
shared login throttling and existing account roles. Password changes revoke old
sessions when the new secret version is deployed. The single-admin helper
replaces the configured account list; team accounts require a complete reviewed
account list in Secret Manager. There is no email password-reset integration.

## Cloud Shell preparation

Run from a checkout of the merged main branch in **Google Cloud Shell**. Do not
paste passwords or secret values into chat. The preparation script prompts
privately for an admin password of at least 15 characters and stores only its
hash in `recruitment-password-accounts`.

```bash
gh auth status
git clone https://github.com/srinu7893/recruitment-screening-assistant.git recruitment-production
cd recruitment-production
python3 -m venv .cloud-setup-venv
.cloud-setup-venv/bin/pip install -r requirements.txt
.cloud-setup-venv/bin/python -m scripts.production_setup prepare
```

If GitHub CLI is not signed in, run `gh auth login` first. If the checkout already
exists, enter it and pull main instead of cloning again. Use a clean checkout.

Preparation creates `recruitment_production` in the existing Neon database,
owned by the existing recruitment login. Owner credentials are read privately
from existing Secret Manager entries only to provision that schema. Existing
payment and demonstration tables are untouched. Separate schema locks prevent
the old demo worker from claiming new production jobs. The existing direct
database URL secret is reused; its legacy `demo` name does not change its value.

The new Cloud Run service is `recruitment-screening`. A private bootstrap service
reserves its canonical URL. Preparation updates the GitHub environment
`recruitment-cloud` with password/rules configuration and the pinned account
secret version. Existing workload identity and deployer credentials are reused.

## Deploy and verify

Wait until the Tests workflow passes on the exact main commit, then run:

```bash
gh workflow run deploy-cloud.yml --repo srinu7893/recruitment-screening-assistant --ref main
gh run list --repo srinu7893/recruitment-screening-assistant --workflow deploy-cloud.yml --limit 3
```

After that deployment succeeds:

```bash
.cloud-setup-venv/bin/python -m scripts.production_setup publish
```

Publication checks the ready revision uses password authentication and the rules
provider before allowing access to its login page. Native Google IAP is disabled
for the new service. All data APIs still require an application session. An
organization policy that disallows public Cloud Run invocation must be resolved
by the organization owner; do not disable application authentication.

Publication prompts privately for the admin login and runs a real HTTPS smoke
test: anonymous denial, login, secure cookie, CSRF, Neon, synthetic TXT upload
through the scanner, durable worker, evidence assessment, note persistence,
export, record deletion and logout. It leaves a clearly named synthetic approved
role in role history. A failed test can leave a synthetic record for inspection.

To rerun verification independently:

```bash
.cloud-setup-venv/bin/python -m scripts.cloud_smoke --url YOUR_CANONICAL_SERVICE_URL
```

The old `recruitment-screening-demo` service is retained for rollback and may
continue incurring minimum-instance costs. Retire it after verifying the new
service and deciding whether to retain demonstration access. A service rename
alone is not evidence of production readiness: complete the live smoke test,
backup/restore exercise, access review and a recruiter pilot before real use.
