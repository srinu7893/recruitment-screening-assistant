# Daily encrypted backups

The **Back up recruitment records** workflow creates a recruitment-only encrypted
snapshot in a private Cloud Storage bucket. It runs at 02:00 IST (20:30 UTC) when
enabled. GitHub can delay scheduled runs; this is not a guaranteed recovery-point
SLA. Enable GitHub workflow failure notifications and check recent successful runs.

The database is opened read-only, without running application migrations. The
workflow cannot restore production, delete backups or retrieve older archives.
The encryption key stays in a pinned Secret Manager version and is never uploaded
as an artifact. Application and account records remain sensitive even encrypted.

## One-time setup in the owner's authenticated Cloud Shell

Run after this release is merged. These commands create resources and incur
storage charges. The example deletes snapshots after 30 days; confirm that period
with the data owner before using it. Bucket soft-delete settings can retain
deleted objects longer. Never delete an encryption-key version while any backup
using it must remain recoverable.

```bash
set -euo pipefail
cd ~/recruitment-production
git pull --ff-only origin main
export PROJECT_ID=project-c9bd3d0e-266f-47bf-852
export PROJECT_NUMBER=52916499838
export REPO=srinu7893/recruitment-screening-assistant
export BUCKET="${PROJECT_ID}-recruitment-backups"
export BACKUP_SA="recruitment-backup@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create recruitment-backup --project="$PROJECT_ID"
gcloud iam service-accounts add-iam-policy-binding "$BACKUP_SA" \
  --project="$PROJECT_ID" --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/recruitment-github-pool/attribute.repository_id/1416543360"

printf '%s' '{"rule":[{"action":{"type":"Delete"},"condition":{"age":30}}]}' > /tmp/recruitment-backup-lifecycle.json
gcloud storage buckets create "gs://${BUCKET}" --project="$PROJECT_ID" \
  --location=us-central1 --uniform-bucket-level-access --public-access-prevention \
  --lifecycle-file=/tmp/recruitment-backup-lifecycle.json
gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" \
  --member="serviceAccount:${BACKUP_SA}" --role=roles/storage.objectCreator

# Generate directly into Secret Manager. Never print or paste the key.
.cloud-setup-venv/bin/python -c 'from cryptography.fernet import Fernet; import sys; sys.stdout.buffer.write(Fernet.generate_key())' | \
  gcloud secrets create recruitment-backup-key --project="$PROJECT_ID" --data-file=-
for SECRET in recruitment-demo-database-url recruitment-backup-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" --project="$PROJECT_ID" \
    --member="serviceAccount:${BACKUP_SA}" --role=roles/secretmanager.secretAccessor
done

printf '%s' "$BACKUP_SA" | gh secret set BACKUP_SERVICE_ACCOUNT --repo "$REPO" --env recruitment-cloud
export BUCKET
.cloud-setup-venv/bin/python - <<'PY' | gh variable set RECRUITMENT_BACKUP_CONFIG_JSON --repo "$REPO" --env recruitment-cloud
import json,os
print(json.dumps({"project":os.environ["PROJECT_ID"], "schema":"recruitment_production",
 "bucket":os.environ["BUCKET"],
 "database_secret":{"name":"recruitment-demo-database-url","version":"1"},
 "key_secret":{"name":"recruitment-backup-key","version":"1"}}))
PY
gh workflow run backup-cloud.yml --repo "$REPO" --ref main
```

Use the production deployment's actual database secret/schema if they have
changed. The existing `WIF_PROVIDER` environment secret is reused; deployment's
service account is not used for backups. If a resource already exists, inspect
and reuse it rather than adding a new key version or replacing its policy.

After the manual run succeeds, check the snapshot in the bucket and perform an
isolated restore with its pinned key. Copy the object URL from the workflow's
successful JSON report (contains no resume text or credentials):

```bash
.cloud-setup-venv/bin/python -m scripts.cloud_ops restore-drill \
  --archive gs://YOUR_BUCKET/snapshots/YOUR_OBJECT.encrypted \
  --key-secret recruitment-backup-key --key-version 1
```

The owner downloads the encrypted object and key to a temporary directory,
restores into a new isolated schema, checks table counts, drops only that schema
and removes the temporary files. It never replaces production records. Owner
Neon secrets are needed only for creating/dropping the isolated schema.

Then enable scheduling:

```bash
gh variable set RECRUITMENT_BACKUPS_ENABLED --repo "$REPO" --body true
```

Set that repository variable to `false` to pause scheduling. Manual runs remain
available. A successful upload proves creation, not recovery: retain the separate
key reference and run restore drills. Without `--archive`, the drill still checks
the manual Cloud Shell backup path. Keep all keys private and never commit them.

References: [private bucket creation](https://docs.cloud.google.com/storage/docs/creating-buckets),
[Object Creator permissions](https://docs.cloud.google.com/storage/docs/access-control/iam-roles).
