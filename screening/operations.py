"""Human review, comparison, calibration and operational summaries."""
from collections import Counter
import copy
from datetime import datetime, timezone, timedelta
import re

from .contracts import text
from .core import evaluate
from .storage import ConflictError, now


def effective_result(run):
    return run.get("review_result") or run.get("result")


def preview(run, required_ids):
    if not run.get("result"):
        raise ValueError("Run has no valid assessment")
    criteria = copy.deepcopy(run["role_snapshot"]["criteria"])
    ids = {c["id"] for c in criteria}
    if not isinstance(required_ids, list) or any(not isinstance(x, str) or x not in ids for x in required_ids):
        raise ValueError("Unknown required criterion")
    for criterion in criteria:
        criterion["required"] = criterion["id"] in required_ids
    result = evaluate({"role_version": run["role_version"], "criteria": criteria,
                       "sources": {run["source"]["source_id"]: run["source"]["text"]},
                       "assessments": effective_result(run)["assessments"]})
    return {"preview_only": True, "recommendation": result["recommendation"],
            "required_ids": required_ids, "human_review_required": True}


def review(store, run_id, body, actor):
    decision = body.get("decision")
    if decision not in ("advance", "reject", "hold"):
        raise ValueError("Decision must be advance, reject or hold")
    reason = text(body.get("reason"), "reason", 2000)

    def change(run):
        if run.get("demo") and decision != "hold":
            raise ValueError("Demo results support hold only; use evaluated live results for decisions")
        run.setdefault("decisions", []).append({"decision": decision, "reason": reason,
                                               "actor": actor, "at": now()})
        run["status"] = "completed" if decision != "hold" else "awaiting_review"
    return store.mutate_run(run_id, body.get("revision"), actor, "decision_recorded", change)


def note(store, run_id, body, actor):
    content = text(body.get("text"), "note", 2000)
    return store.mutate_run(run_id, body.get("revision"), actor, "note_added",
                            lambda run: run.setdefault("notes", []).append({"text": content, "actor": actor, "at": now()}))


def correct(store, run_id, body, actor):
    reason = text(body.get("reason"), "reason", 2000)
    assessment = body.get("assessment")
    if not isinstance(assessment, dict):
        raise ValueError("Assessment is required")

    def change(run):
        result = copy.deepcopy(effective_result(run))
        key = assessment.get("criterion_id")
        if key not in {c["id"] for c in run["role_snapshot"]["criteria"]}:
            raise ValueError("Unknown criterion")
        rows = [assessment if a["criterion_id"] == key else a for a in result["assessments"]]
        checked = evaluate({"role_version": run["role_version"], "criteria": run["role_snapshot"]["criteria"],
                            "sources": {run["source"]["source_id"]: run["source"]["text"]}, "assessments": rows})
        result.update(checked)
        by_id = {c["id"]: c for c in run["role_snapshot"]["criteria"]}
        result["follow_up_questions"] = [
            {"criterion_id": row["criterion_id"], "question": by_id[row["criterion_id"]]["question"]}
            for row in result["assessments"] if row["status"] != "meets"
        ]
        run["review_result"] = result
        run.setdefault("corrections", []).append({"assessment": assessment, "reason": reason, "actor": actor, "at": now()})
        # A material correction invalidates the active decision, preserving its history.
        if run.get("decisions"):
            run["decisions"].append({"decision": "hold", "reason": "Assessment corrected; review again.", "actor": actor, "at": now()})
        run["status"] = "awaiting_review"
    return store.mutate_run(run_id, body.get("revision"), actor, "assessment_corrected", change)


def summary(run, duplicates=0):
    result = effective_result(run) or {}
    rows = result.get("assessments", [])
    evidenced = sum(bool(a.get("evidence")) for a in rows)
    return {"run_id": run["run_id"], "candidate_id": run["candidate_id"],
            "role_version": run["role_version"], "status": run["status"],
            "created_at": run.get("created_at", run["events"][0]["at"]),
            "recommendation": result.get("recommendation"), "demo": run.get("demo", False),
            "decision": run.get("decisions", [{}])[-1].get("decision"),
            "evidence_coverage": {"supported": evidenced, "total": len(rows)},
            "duplicate_count": duplicates, "error": run.get("error"),
            "source_kind": run["source"].get("kind", "paste")}


def overview(store):
    runs = store.list_runs()
    hashes = Counter(r["source"]["sha256"] for r in runs)
    rows = [summary(r, hashes[r["source"]["sha256"]] - 1) for r in runs]
    return {"runs": rows, "metrics": {
        "total": len(rows), "awaiting_review": sum(r["status"] == "awaiting_review" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "completed": sum(r["status"] == "completed" for r in rows),
        "demo": sum(r["demo"] for r in rows),
        "by_recommendation": dict(Counter(r["recommendation"] for r in rows if r["recommendation"]))
    }}


def compare(store, ids):
    if not isinstance(ids, list) or not 2 <= len(ids) <= 5 or len(set(ids)) != len(ids):
        raise ValueError("Choose 2 to 5 distinct runs")
    runs = [store.get_run(text(x, "run id", 120)) for x in ids]
    if len({r["role_version"] for r in runs}) != 1 or any(not r["result"] for r in runs):
        raise ValueError("Compare assessed profiles for the same role version")
    return {"role_version": runs[0]["role_version"], "criteria": runs[0]["role_snapshot"]["criteria"],
            "candidates": [{"run_id": r["run_id"], "assessments": effective_result(r)["assessments"]} for r in runs]}


def interview_kit(run):
    if not run["result"]:
        raise ValueError("Assessment required")
    rows = {a["criterion_id"]: a for a in effective_result(run)["assessments"]}
    return {"run_id": run["run_id"], "questions": [{"criterion_id": c["id"],
             "question": c["question"], "focus": rows[c["id"]]["status"],
             "evidence": rows[c["id"]]["evidence"],
             "rubric": "Record specific examples, personal contribution and observable results."}
             for c in run["role_snapshot"]["criteria"]]}


def draft_criteria(description):
    text(description, "job description", 12_000)
    lines = [re.sub(r"^\s*[-*•\d.)]+\s*", "", x).strip() for x in description.splitlines() if x.strip()]
    return {"draft": True, "method": "line-based draft; recruiter approval required", "criteria": [
        {"id": f"criterion-{i+1}", "description": line[:1000], "required": False,
         "question": f"Describe your relevant experience with: {line[:350]}"}
        for i, line in enumerate(lines[:25])
    ]}


def expire(store, days, actor):
    if type(days) is not int or not 1 <= days <= 3650:
        raise ValueError("Retention must be 1 to 3650 days")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    deleted = 0
    for run in store.list_runs():
        created = datetime.fromisoformat(run.get("created_at", run["events"][0]["at"]))
        if created < cutoff:
            try:
                store.delete_run(run["run_id"], actor)
                deleted += 1
            except ConflictError:
                pass
    return {"deleted": deleted, "retention_days": days}
