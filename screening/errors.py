"""Stable user-facing processing guidance; never include raw exception text."""
MESSAGES = {
 'job_failed': 'Processing stopped before a review was ready. Retry after checking the service.',
 'processing_failed': 'The profile could not be processed. Check the service and retry.',
 'provider_unavailable': 'The screening service could not be reached. Try again shortly.',
 'invalid_model_output': 'The assessment failed its evidence checks. Inspect the source and retry.',
 'interrupted_retry_with_new_id': 'The worker restarted during processing. Start an explicit retry.',
 'restore_requires_retry': 'This job came from a backup. Review it and start an explicit retry.',
 'provider_configuration_changed': 'Screening settings changed. Retry with the current settings.'
}


def processing_error(code):
    return MESSAGES.get(code, 'Screening did not finish. Inspect the source and retry; contact an administrator if it continues.') if code else None
