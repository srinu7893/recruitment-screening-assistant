# Team workflows and operating checks

Implemented in the team-workflow feature release. These instructions apply after
deploying that release; they do not mean the current live service was upgraded.

## 1. Set up matching

Open **Roles & criteria**. Write each requirement and add **Matching phrases**,
one phrase per line. You no longer need to put quotes into the requirement.
Open **Preview matching before approval**, paste sample text and inspect the
phrases and source excerpts. Preview saves neither the role nor the sample.

Rules-mode approval is blocked when any criterion has no phrases. Existing role
versions with quoted phrases still work. Existing reviews and roles are not
rewritten. Matching remains literal and produces partial evidence for review;
this release does not infer proficiency, years, negation or synonyms.

## 2. Use available sources

Uploads are processed automatically without enabling an intake schedule.
**Automation** hides unavailable folder/feed controls and disables scheduled
intake when no source is configured. Cloud Run uses uploads or a configured feed;
folder watching is for local installations.

For an approved real JSON feed, run in Cloud Shell after creating its role:

```bash
cd ~/recruitment-production
git pull --ff-only origin main
.cloud-setup-venv/bin/python -m scripts.configure_source \
  --url https://YOUR_APPROVED_HOST/resumes.json \
  --role-version YOUR_APPROVED_ROLE_VERSION
```

This updates the GitHub environment configuration, not the running service.
For authenticated feeds add `--token-secret NAME --token-version NUMBER` and
grant the runtime service account Secret Accessor on that secret. Keep the token
out of the URL and terminal output. Deploy the workflow, then use **Connections →
Sync now** to verify an import. In Automation choose the role, feed and interval,
then enable automatic intake. The configuration client starts polling paused.
After Automation settings are saved, they own both scheduling and pausing;
legacy environment polling is suppressed even while the agent is paused.

Feed contract: `{"candidates":[{"external_id":"source-id","profile_text":"resume text"}]}`.
Repeated unchanged records reuse existing jobs. An approved live URL and source
credentials are still required; a synthetic or mocked test is not a real ATS test.

The rules implementation is versioned as `literal-evidence-v2`. Older queued
jobs are not silently evaluated with changed matching behavior: a configuration
mismatch produces an explicit retry failure. Previously saved reviews remain
unchanged. The manager loader retains matching saved fixtures across upgrades.

## 3. Manage people

In password mode, open **Account → Team accounts** as an administrator. Create
an individual username, display name, role and initial password. Confirm each
change with your current admin password. Share the initial password privately;
the user can change it in **Account**.

- **Save access** changes role, name or disabled status. Disabled accounts cannot
  sign in, and changes revoke their existing sessions.
- The last enabled administrator cannot be disabled or demoted.
- Names remain in old review history; changing a name does not rewrite earlier
  notes or assignments. Usernames are unique and accounts are disabled rather
  than deleted to retain attribution.
- Account lists never return password hashes. Secret values are not audited.

Bootstrap accounts are read from the pinned Secret Manager account list. Managed
changes are stored as PostgreSQL overrides and persist across replicas/restarts.
Once an account has an override, changing the bootstrap secret does not replace
its managed password. Use the account UI or the recovery process below.
Existing sessions from the earlier version are invalidated once on upgrade.
Prefer roll-forward fixes after managed account changes: older application
binaries do not enforce these database account overrides. A restore/cutover must
also review recovered account access and credentials before opening the service.

## 4. Recover a password

An administrator confirms their own password and chooses **Issue recovery code**
for the enabled account. Send the code privately. It expires after 15 minutes,
works once, and is replaced if another code is issued. The user opens **Reset
password with a recovery code** on the login screen. After the reset they sign
in normally; previous sessions are revoked. There is no email-delivery service.

If the only administrator cannot log in, the authorized Cloud Shell owner can run:

```bash
.cloud-setup-venv/bin/python -m scripts.cloud_ops recovery --username admin
```

That command deliberately displays a private one-use code. Do not paste its
output into chat, tickets or shared logs. Use it on the login recovery form.

## 5. Retry failed screening

Open **Processing queue** or **Automation → All processing jobs**. Administrators
see a readable error and **Retry screening**. A retry creates a new job linked to
the failed original. Repeated clicks reuse that retry; to retry a failed child,
use that child's action. Original failures and review history remain unchanged.
If the source was removed, upload it again. Inbox parsing failures retain their
separate **Retry import** action. No work is silently repeated after a crash.

## 6. Monitor operations

Administrators can use **Account → Check operations** for counts, queue age,
worker heartbeat and a scanner signature check. The app emits a content-free
`screening_operations` JSON report every minute in Cloud Run. Warnings cover a
missing/stale worker heartbeat, queue wait over five minutes, failed jobs, scanner
health and database access. These are operational signals, not availability SLAs.

Create a Cloud Monitoring notification channel, then install the policy:

```bash
.cloud-setup-venv/bin/python -m scripts.install_operations_alert \
  --channel projects/PROJECT_ID/notificationChannels/CHANNEL_NUMBER
```

Use the real channel resource in the deployment project. The installer avoids a
duplicate name and uses the [Cloud Monitoring log-alert API](https://docs.cloud.google.com/logging/docs/alerting/log-based-alerts).
Verify notification delivery with a controlled warning. This policy needs app
logs; add independent Cloud Run uptime/startup alerts for failures before the
application can emit them. Policies and channel delivery cannot be verified
without access to the actual project/channel.

## 7. Back up and verify restore

Run from the authenticated owner Cloud Shell:

```bash
.cloud-setup-venv/bin/python -m scripts.cloud_ops backup
.cloud-setup-venv/bin/python -m scripts.cloud_ops restore-drill
```

Backups contain only recruitment application tables in a consistent snapshot.
They are encrypted and integrity-protected with Fernet. Archives are under
`data/cloud-backups`; the key is `data/cloud-backup-key.txt`. Keep the key private
and store it separately from the archives, along with the deployment's pinned
Secret Manager references. Backup account overrides contain password hashes and
must remain encrypted. Protect the archive/key with the team's access policy.

The drill restores into a new random schema, verifies table counts, then drops
only that schema. It does not replace production tables. Existing bootstrap
account secrets remain separate deployment prerequisites. Session/recovery
tokens and worker heartbeat are excluded. Restored active jobs become explicit
retry failures so a restore cannot silently repeat screening work. Original
uploaded binaries are not retained by the application and are not in the backup.

These commands implement a manual backup/drill process. Configure scheduling,
secure archive/key storage and a retention policy for ongoing operations. A
restore into a nonempty target is refused; production recovery requires a planned
cutover to a separately provisioned empty schema.

An opt-in [daily encrypted backup workflow](SCHEDULED_BACKUPS.md) is now available.
It requires a separate backup identity, private bucket, pinned encryption-key
secret and an explicit enable flag. It does not use the deployer's identity.

## 8. Check a small workload

```bash
.cloud-setup-venv/bin/python -m scripts.load_check \
  --url https://recruitment-screening-fddyka6g2a-uc.a.run.app \
  --count 10 --workers 2
```

Enter the application admin login privately. The command uploads synthetic TXT
resumes through the scanner, waits for background results, checks evidence and
reports measured timings. Successful test runs are deleted; the labelled test
role remains. Failed tests can leave labelled records for investigation. Limits
are 20 resumes and four submitters to respect the normal request limit. This is
a small workload rehearsal, not a high-volume capacity certification.

## Release verification

1. Run the backend, PostgreSQL and browser checks; wait for CI on main.
2. Deploy through the existing Cloud Run workflow.
3. Run `scripts.cloud_smoke` with the production URL.
   This also creates a synthetic viewer, checks permissions and one-use recovery,
   verifies revoked sessions, and disables that account in cleanup. Its disabled
   account/audit history remains. No existing account password is changed.
4. Verify account creation/recovery using a disposable test account, source import
   with an approved source, notification delivery, restore drill and workload
   timings. Record which checks actually passed; do not infer live verification
   from local tests.
