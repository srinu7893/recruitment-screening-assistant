"""Deterministic routing; no model calls or final hiring decisions."""

STATUSES = {"meets", "partial", "not_demonstrated", "unmet"}


def nonempty_string(value):
    return isinstance(value, str) and bool(value.strip())


def evaluate(payload):
    """Validate an assessment envelope or raise ValueError."""
    if not isinstance(payload, dict):
        raise ValueError("Input must be an object")
    version = payload.get("role_version")
    criteria = payload.get("criteria")
    sources = payload.get("sources")
    assessments = payload.get("assessments")
    if not nonempty_string(version):
        raise ValueError("role_version is required")
    if not isinstance(criteria, list) or not criteria:
        raise ValueError("criteria must be a nonempty list")
    if not isinstance(sources, dict) or any(
        not nonempty_string(k) or not isinstance(v, str) for k, v in sources.items()
    ):
        raise ValueError("sources must map source IDs to text")
    if not isinstance(assessments, list):
        raise ValueError("assessments must be a list")
    by_id = {}
    for criterion in criteria:
        if not isinstance(criterion, dict):
            raise ValueError("Invalid criterion")
        key = criterion.get("id")
        if not nonempty_string(key) or key in by_id:
            raise ValueError("Criterion IDs must be nonempty and unique")
        if type(criterion.get("required")) is not bool:
            raise ValueError("required must be a boolean")
        by_id[key] = criterion
    assessed = {}
    for item in assessments:
        if not isinstance(item, dict):
            raise ValueError("Invalid assessment")
        key, status = item.get("criterion_id"), item.get("status")
        if not nonempty_string(key) or key not in by_id or key in assessed:
            raise ValueError("Unknown or repeated assessment criterion")
        if not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Invalid assessment status")
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list):
            raise ValueError("evidence must be a list")
        if status != "not_demonstrated" and not evidence:
            raise ValueError("A substantive assessment requires evidence")
        for ref in evidence:
            if not isinstance(ref, dict):
                raise ValueError("Invalid evidence reference")
            source_id, quote = ref.get("source_id"), ref.get("quote")
            if not nonempty_string(source_id) or source_id not in sources:
                raise ValueError("Unknown evidence source")
            if not nonempty_string(quote) or quote not in sources[source_id]:
                raise ValueError("Evidence quote is not present in source")
        assessed[key] = {"criterion_id": key, "status": status, "evidence": evidence}
    rows = [assessed.get(key, {"criterion_id": key, "status": "not_demonstrated", "evidence": []}) for key in by_id]
    required = [row for row in rows if by_id[row["criterion_id"]]["required"]]
    if any(row["status"] == "unmet" for row in required):
        recommendation = "review_non_advancement"
    elif not required or any(row["status"] != "meets" for row in required):
        recommendation = "needs_clarification"
    else:
        recommendation = "recommend_interview"
    return {"role_version": version, "recommendation": recommendation,
            "human_review_required": True, "assessments": rows}
