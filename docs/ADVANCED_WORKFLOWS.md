# ATS imports, document scanning and interview evidence

## Completion and live acceptance

Implemented: selected-resume Greenhouse v3 import, ClamAV scan gate and Cloud Run sidecar, human interview scorecards, expanded evaluation diagnostics. Unit/contract tests do not verify a customer's ATS credentials or production signature updates. No automatic hiring decisions or outbound ATS updates are introduced.

## Cloud document scanning

The deployment workflow builds both the web and scanner images and pins both digests. The scanner runs alongside each Cloud Run instance, with 1 CPU and 3 GiB allocated in addition to the web container. This increases hosting cost. It downloads signatures before opening port 3310 and runs FreshClam for updates. The port is internal to the instance; do not publish it through a separate public service. Web startup depends on the scanner's TCP startup probe.

Cloud file extraction defaults to `SCREENING_SCAN_MODE=clamd` and cannot be disabled with `off`. Only an exact clean verdict proceeds to extraction. Unknown responses, detection, network errors, scan limits, or missing/stale signature dates block the upload. Signature age is capped at 72 hours; both containers use UTC. PDFs, DOCX and TXT uploads, remote PDFs and Greenhouse resume files pass through the same scan gate. Pasted text, CSV fields and web HTML are text inputs, not binary attachments; their content remains untrusted by the model.

The scanner streams bytes over loopback, has bounded responses/timeouts, and retains no original files. Encrypted archives and scan-limit violations are treated as detections by the supplied daemon configuration. This is one protection layer, not a guarantee that all malicious documents can be detected. Existing extraction subprocess and resource limits remain active.

Before enabling real resumes, verify that FreshClam can reach its update service from your cloud network, the image starts within Cloud Run's startup deadline, signatures stay fresh across several days, and encrypted/oversized documents are blocked. Investigate scanner logs if uploads stop; do not bypass the gate. CI uses a harmless custom signature with a real daemon to verify detection. That CI test deliberately mocks the signature-age check because its synthetic database has no daily.cvd timestamp; date rejection has separate tests.

Non-cloud development can set `SCREENING_SCAN_MODE=off`; extraction includes an explicit unscanned warning. For a non-Cloud-Run production host, explicitly set `clamd` and run the scanner in the same private network namespace. Never expose unauthenticated clamd to the internet.

## Greenhouse setup and use

This is a read-only Harvest v3 **custom integration**, using OAuth client credentials. Create credentials with attachment-read permissions in your Greenhouse account. Store `GREENHOUSE_CLIENT_ID` and `GREENHOUSE_CLIENT_SECRET` in Secret Manager and add pinned references to the deployment configuration's `secrets` object. Configure `greenhouse_attachment_hosts` as comma-separated exact hosts used by your account's download and redirect endpoints. Do not use wildcards. The OAuth/API hosts are fixed in code; bearer tokens are never forwarded to file hosts.

In Connections, an administrator enters the candidate ID, resume attachment ID and an existing approved role version. The connector requests that exact attachment and validates the candidate association and resume classification before downloading. It follows at most three redirects, checking HTTPS, host allowlist and public DNS addresses on every hop. Signed URLs, raw OAuth responses and credentials are not saved in candidate records. Repeated identical imports deduplicate; each selected attachment remains identifiable by candidate and attachment IDs.

Missing permissions, expired credentials, rate limits, blocked hosts or a nonmatching attachment fail visibly. A 401 gets one token renewal retry. There is no broad automatic account crawl or ATS writeback. Validate the integration first with an authorized fictional test candidate; test an expired credential and an unexpected redirect host too.

## Interview scorecards

Open a reviewed profile and select **Add interview scorecard**. Record the interview stage and each criterion's observed evidence: demonstrated, needs follow-up or not observed. Each saved card records the authenticated interviewer, time and role version. Cards are append-only and included in the existing review JSON export. A concurrent edit gets a revision conflict. New evidence reopens a completed decision as hold, preserving the prior decision history. Resume/model assessments remain separate from interviewer observations. Demo profiles still permit hold only.

## Evaluation reports

The existing cloud evaluation workflow now reports invalid outputs separately, overall criterion agreement, per-criterion matched/compared counts, a status confusion table, and recommendation agreement. A human review rubric covers semantic faithfulness, missing evidence, approved job criteria and prompt injection. Agreement uses only valid outputs; review the invalid count alongside it. The six fictional examples are regression fixtures, not a production accuracy benchmark. Numeric release targets and a representative recruiter-labeled pilot remain required before trusting live model quality.

References: [Greenhouse authentication](https://harvestdocs.greenhouse.io/docs/authentication), [attachments](https://harvestdocs.greenhouse.io/reference/get_v3-attachments), [ClamD protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html).
