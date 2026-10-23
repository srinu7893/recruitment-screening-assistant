"""Operational counts without resume text, identities, credentials or job IDs."""
from datetime import datetime, timezone
import time


def snapshot(store, queue=None):
    current=time.time()
    with store.connect() as db:
        counts=dict(db.execute('SELECT status, count(*) FROM jobs GROUP BY status').fetchall())
        heartbeat=db.execute('SELECT at FROM worker_heartbeats WHERE id = ?', ('screening',)).fetchone()
        documents=db.execute("SELECT document FROM jobs WHERE status = 'queued'").fetchall()
        failures=db.execute("SELECT document FROM jobs WHERE status = 'failed'").fetchall()
    import json
    ages=[max(0,current-datetime.fromisoformat(json.loads(r[0])['created_at']).timestamp()) for r in documents]
    heartbeat_age=max(0,current-heartbeat[0]) if heartbeat else None
    warnings=[]
    if store.backend=='postgresql' and (heartbeat_age is None or heartbeat_age>120):
        warnings.append('screening_worker_heartbeat_missing_or_stale')
    if max(ages,default=0)>300:
        warnings.append('screening_queue_wait_over_five_minutes')
    unresolved=sum(not json.loads(row[0]).get('retry_job_id') for row in failures)
    if unresolved:
        warnings.append('failed_jobs_need_review')
    if queue and queue.last_error:
        warnings.append('this_instance_worker_connection_error')
    return {'event':'screening_operations','at':datetime.now(timezone.utc).isoformat(),
            'severity':'WARNING' if warnings else 'INFO','database':'connected',
            'jobs':counts,'unresolved_failed_jobs':unresolved,'oldest_queued_seconds':round(max(ages,default=0)),
            'worker_heartbeat_age_seconds':round(heartbeat_age) if heartbeat_age is not None else None,
            'warnings':warnings}
