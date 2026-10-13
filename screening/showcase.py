"""Explicit, reproducible fictional scenarios; never a substitute for live evaluation."""
import argparse
import copy
import json
from pathlib import Path

from .contracts import validate_output, validate_role
from .storage import Store, ConflictError
from .workflow import ScreeningService


def dataset():
    return json.loads(Path(__file__).with_name("fixtures").joinpath("production_support.json").read_text())


class FixtureProvider:
    name = "showcase"
    model = "authored-production-support-v1"
    is_demo = True

    def __init__(self, profile):
        self.profile = profile

    def analyze(self, role, source_id, profile):
        if profile != self.profile["profile_text"] or role["role_version"] != dataset()["role"]["role_version"] or role["criteria"] != dataset()["role"]["criteria"]:
            raise ValueError("Showcase fixtures cannot evaluate arbitrary input")
        def evidence(quotes):
            return [{"source_id": source_id, "quote": quote} for quote in quotes]
        return {"facts": [],
                "summary": [{"text": claim["text"], "evidence": evidence(claim["quotes"])} for claim in self.profile["summary"]],
                "assessments": [{"criterion_id": a["criterion_id"], "status": a["status"],
                                 "rationale": a["rationale"], "evidence": evidence(a["quotes"])} for a in self.profile["assessments"]]}


def export_dataset():
    data = dataset()
    validate_role(data["role"])
    for profile in data["profiles"]:
        provider = FixtureProvider(profile)
        profile["result"] = validate_output(provider.analyze(data["role"], profile["id"], profile["profile_text"]),
                                            data["role"], profile["id"], profile["profile_text"])
    return data


def seed(store, actor="showcase-operator"):
    data = export_dataset()  # Validate every quote before creating any record.
    role = copy.deepcopy(data["role"])
    role["approved_by"] = actor
    try:
        existing = store.get_role(role["role_version"])
        if existing["criteria"] != role["criteria"] or existing["title"] != role["title"]:
            raise ConflictError("Showcase role version exists with different criteria")
    except KeyError:
        store.create_role(role)
    records = []
    for profile in data["profiles"]:
        service = ScreeningService(store, FixtureProvider(profile))
        run = service.screen({"request_id": "showcase-" + profile["id"],
                              "role_version": role["role_version"], "profile_text": profile["profile_text"]},
                             {"kind": "showcase", "display_name": profile["id"] + " · " + profile["title"],
                              "scenario": profile["scenario"], "result_origin": "authored_fixture_not_live_model"})
        records.append(run["run_id"])
    store.audit(actor, "showcase_loaded", "fictional-production-support")
    return {"run_ids": records, "role_version": role["role_version"], "notice": data["notice"]}


def main():
    parser = argparse.ArgumentParser(description="Load six fictional, authored production-support scenarios")
    parser.add_argument("--db", default="data/showcase.sqlite3")
    args = parser.parse_args()
    result = seed(Store(args.db))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
