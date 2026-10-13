import copy
import json
from pathlib import Path
import unittest

from screening.core import evaluate


class ScreeningTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads((Path(__file__).resolve().parents[1] / "examples/assessment.json").read_text())

    def test_supported_requirement_recommends_interview_with_review(self):
        result = evaluate(self.payload)
        self.assertEqual(result["recommendation"], "recommend_interview")
        self.assertTrue(result["human_review_required"])
        self.assertEqual(result["assessments"][1]["status"], "not_demonstrated")

    def test_missing_requirement_needs_clarification(self):
        self.payload["assessments"] = []
        self.assertEqual(evaluate(self.payload)["recommendation"], "needs_clarification")

    def test_partial_requirement_needs_clarification(self):
        self.payload["assessments"][0]["status"] = "partial"
        self.assertEqual(evaluate(self.payload)["recommendation"], "needs_clarification")

    def test_explicit_unmet_routes_to_review(self):
        self.payload["sources"] = {"synthetic-resume": "I have never built Python APIs."}
        self.payload["assessments"][0].update(status="unmet", evidence=[{"source_id": "synthetic-resume", "quote": "I have never built Python APIs."}])
        self.assertEqual(evaluate(self.payload)["recommendation"], "review_non_advancement")

    def test_no_required_criteria_does_not_auto_recommend(self):
        for item in self.payload["criteria"]:
            item["required"] = False
        self.assertEqual(evaluate(self.payload)["recommendation"], "needs_clarification")

    def test_invalid_evidence_rejected(self):
        for evidence in ([], [{"source_id": "missing", "quote": "Python"}], [{"source_id": "synthetic-resume", "quote": "AWS expert"}], [{"source_id": "synthetic-resume", "quote": " "}]):
            with self.subTest(evidence=evidence):
                self.payload["assessments"][0]["evidence"] = evidence
                with self.assertRaises(ValueError):
                    evaluate(self.payload)

    def test_invalid_contracts_rejected(self):
        mutations = [
            ("role_version", ""), ("criteria", []), ("sources", []),
            ("assessments", None),
            ("criteria", [{"id": "x", "required": "false"}]),
            ("criteria", self.payload["criteria"] * 2),
            ("assessments", self.payload["assessments"] * 2),
            ("assessments", [{"criterion_id": "unknown", "status": "not_demonstrated"}]),
            ("assessments", [{"criterion_id": "python-api", "status": []}]),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                payload = copy.deepcopy(self.payload)
                payload[key] = value
                with self.assertRaises(ValueError):
                    evaluate(payload)

    def test_input_is_not_modified(self):
        original = copy.deepcopy(self.payload)
        evaluate(self.payload)
        self.assertEqual(self.payload, original)


if __name__ == "__main__":
    unittest.main()
