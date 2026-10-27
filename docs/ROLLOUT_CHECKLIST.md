# Finish the live rollout

The requested matching, source controls, team accounts/recovery and failed-job
retry features are built. Code tests do not mean those changes are live.

## 1. Release from GitHub

After **Tests** passes on the merged main commit, run **Deploy recruitment cloud**
on `main` in GitHub Actions. Deployment still uses the existing production URL.

## 2. Test the deployed application

In your authenticated Cloud Shell:

```bash
cd ~/recruitment-production
git pull --ff-only origin main
.cloud-setup-venv/bin/pip install -r requirements.txt
.cloud-setup-venv/bin/python -m scripts.cloud_smoke \
  --url https://recruitment-screening-fddyka6g2a-uc.a.run.app
```

Enter your admin password privately. This checks login/permissions, recovery,
revoked sessions, phrase preview, operations, upload scanning, background
screening and saved records. It disables its synthetic account and deletes its
synthetic review; role/account audit history remains. Existing users' passwords
are never changed. Revoked session tokens are removed on their next request.

## 3. Complete the connections

| Needed from the owner | What to run |
| --- | --- |
| Approved source URL, role and optional token secret reference | `scripts.configure_source`, then deploy and verify **Sync now** before enabling intake |
| Cloud Monitoring notification-channel resource | `scripts.install_operations_alert`, then verify an actual delivered warning |
| Private backup bucket, pinned key and retention decision | Follow [SCHEDULED_BACKUPS.md](SCHEDULED_BACKUPS.md); run a manual backup and archive restore drill before enabling daily runs |

Resume uploads work without a source connection or AI API account. Do not claim
unattended ATS collection until the approved real source has been tested.

## 4. Rehearse with the team

Run `scripts.load_check` with synthetic records, provision individual users, and
have two reviewers check a representative approved sample. Agree quality and
volume targets before a wider rollout. Literal matches remain evidence to review;
the rules engine does not infer competence, duration, negation or synonyms.

Detailed commands and account/retry instructions: [TEAM_WORKFLOWS.md](TEAM_WORKFLOWS.md).
