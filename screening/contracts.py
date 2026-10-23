"""Strict contracts shared by the model adapter and local workflow."""

from .core import evaluate

MAX_PROFILE_CHARS = 50_000
PROMPT_VERSION = "screening-v1"


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def array(items):
    return {"type": "array", "items": items}


STRING = {"type": "string"}
EVIDENCE = obj({"source_id": STRING, "quote": STRING})
CLAIM = obj({"text": STRING, "evidence": array(EVIDENCE)})
OUTPUT_SCHEMA = obj({
    "facts": array(obj({"category": {"type": "string", "enum": [
        "skill", "experience", "project", "education", "certification", "achievement"
    ]}, "text": STRING, "evidence": array(EVIDENCE)})),
    "summary": array(CLAIM),
    "assessments": array(obj({
        "criterion_id": STRING,
        "status": {"type": "string", "enum": ["meets", "partial", "not_demonstrated", "unmet"]},
        "rationale": STRING, "evidence": array(EVIDENCE)
    }))
})


def validate_shape(value, schema):
    """Validate only the schema subset defined above; not a general JSON Schema engine."""
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value, dict) or set(value) != set(schema["properties"]):
            raise ValueError("Object fields do not match the contract")
        for key, child in schema["properties"].items():
            validate_shape(value[key], child)
    elif kind == "array":
        if not isinstance(value, list) or len(value) > 100:
            raise ValueError("Expected an array with at most 100 items")
        for item in value:
            validate_shape(item, schema["items"])
    elif kind == "string":
        if not isinstance(value, str) or not value.strip() or len(value) > 6000:
            raise ValueError("Expected nonempty text of at most 6000 characters")
        if "enum" in schema and value not in schema["enum"]:
            raise ValueError("Unsupported enum value")


def text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text of at most {limit} characters")
    return value


def validate_role(role):
    if not isinstance(role, dict) or set(role) != {
        "role_version", "title", "criteria", "approved_by"
    }:
        raise ValueError("Role requires role_version, title, criteria and approved_by")
    text(role["role_version"], "role_version", 120)
    text(role["title"], "title", 200)
    text(role["approved_by"], "approved_by", 120)
    if not isinstance(role["criteria"], list) or not 1 <= len(role["criteria"]) <= 25:
        raise ValueError("Provide 1 to 25 approved job-related criteria")
    for criterion in role["criteria"]:
        required = {'id', 'description', 'required', 'question'}
        if not isinstance(criterion, dict) or not required.issubset(criterion) or set(criterion)-required-{'phrases'}:
            raise ValueError("Criterion requires id, description, required and question")
        text(criterion["id"], "criterion id", 100)
        text(criterion["description"], "criterion description", 1000)
        text(criterion["question"], "clarification question", 500)
        if 'phrases' in criterion:
            phrases = criterion['phrases']
            if not isinstance(phrases, list) or len(phrases) > 12:
                raise ValueError('Provide at most 12 matching phrases per criterion')
            for phrase in phrases:
                text(phrase, 'matching phrase', 120)
                if phrase != phrase.strip() or '\n' in phrase or '\r' in phrase:
                    raise ValueError('Matching phrases must be trimmed, single-line text')
            if len({p.casefold() for p in phrases}) != len(phrases):
                raise ValueError('Matching phrases must be unique within a criterion')
    evaluate({"role_version": role["role_version"], "criteria": role["criteria"],
              "sources": {}, "assessments": []})


def validate_output(output, role, source_id, profile):
    validate_shape(output, OUTPUT_SCHEMA)
    sources = {source_id: profile}
    for claim in output["facts"] + output["summary"]:
        if not claim["evidence"]:
            raise ValueError("Each profile fact and summary claim needs evidence")
        for evidence in claim["evidence"]:
            if evidence["source_id"] != source_id or evidence["quote"] not in profile:
                raise ValueError("Unverifiable profile or summary claim")
    result = evaluate({"role_version": role["role_version"], "criteria": role["criteria"],
                       "sources": sources, "assessments": output["assessments"]})
    # Omitted criteria remain unknown; the model never controls the routing outcome.
    rationale = {a["criterion_id"]: a["rationale"] for a in output["assessments"]}
    criteria = {c["id"]: c for c in role["criteria"]}
    for row in result["assessments"]:
        row["rationale"] = rationale.get(row["criterion_id"], "No assessment was returned.")
    result.update(facts=output["facts"], summary=output["summary"], follow_up_questions=[
        {"criterion_id": row["criterion_id"], "question": criteria[row["criterion_id"]]["question"]}
        for row in result["assessments"] if row["status"] != "meets"
    ])
    return result
