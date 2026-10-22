# Manager demo — simple process

## Prepare once

1. Load the fictional profiles using the command in [README.md](README.md).
2. Sign into the live application with your own account.
3. Open **Review pipeline** and select **DEMO ONLY - Production Support Engineer L2**.
4. Keep one supplied PDF ready to upload during the meeting.

Live loading is confirmed only when the loader prints PASS in Cloud Shell.
Deploying the application does not automatically add these profiles.

## Show five steps

| Step | Screen and action | Explain |
| --- | --- | --- |
| 1. Create role | **Roles & criteria**: show the five requirements | Matching phrases use double quotes, such as `"Linux"`. Role versions preserve earlier reviews. |
| 2. Add resumes | **Add profiles**: select the role and upload a fictional PDF | The app scans it, extracts text and creates a background job. |
| 3. Check processing | **Review pipeline → Processing queue**, or **Automation → All processing jobs** | The worker processes the job automatically. No extra screening click is needed. |
| 4. Review evidence | Open **Review →** for a processed profile | Read each source line. Missing evidence needs a question; a mention needs context. |
| 5. Save decision | Add a fictional note, assign a reviewer and choose **Hold** with a reason | The record keeps the author, notes and decision history. |

## Show three examples

- **DEMO-101:** five criteria have mentions. Read the excerpts; 5/5 is not a pass.
- **DEMO-104:** no mentions. The result is clarification, not rejection.
- **DEMO-105:** two terms occur in negative statements. A word match is not proof
  of a skill.

## Explain the agent in one sentence

“After a resume is submitted, the background worker finds matching phrases,
saves the evidence and prepares a review; the reviewer records the decision.”

Scheduled source intake is separate. Its code is built, but a real feed still
needs configuration. Local folder watching is not available in Cloud Run.

## Close with the next work

1. Make matching phrases easier to enter and preview.
2. Show only available source options in Automation.
3. Add account administration and recovery for team use.
4. Connect one source and verify it live.
5. Complete monitoring, restore and load checks before wider rollout.

Suggested pilot: one role, two reviewers and 20–30 approved sample resumes.
Measure review time, missing evidence, corrections and failed jobs. Report the
results instead of promising a savings percentage before the pilot.
