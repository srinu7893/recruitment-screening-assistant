import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from screening.contracts import MAX_PROFILE_CHARS
from screening.providers import DemoProvider, ProviderError
from screening.storage import ConflictError, Store
from screening.workflow import ScreeningService


class FakeProvider:
    name = "test"
    model = "fake-v1"

    def __init__(self, change=None):
        self.calls = 0
        self.change = change

    def analyze(self, role, source_id, profile):
        self.calls += 1
        evidence = [{"source_id": source_id, "quote": "Built Python APIs"}]
        output = {
            "facts": [{"category": "experience", "text": "Built Python APIs", "evidence": evidence}],
            "summary": [{"text": "Python API development experience", "evidence": evidence}],
            "assessments": [{"criterion_id": "python-api", "status": "meets",
                             "rationale": "Describes Python API implementation.", "evidence": evidence}]
        }
        if self.change:
            self.change(output)
        return output


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "app.sqlite3"
        folder = Path(__file__).resolve().parents[1] / "examples"
        self.role = json.loads((folder / "role.json").read_text())
        self.request = json.loads((folder / "profile-request.json").read_text())
        self.provider = FakeProvider()
        self.service = ScreeningService(Store(self.path), self.provider)
        self.service.create_role(self.role)

    def test_end_to_end_persistence_and_evidence(self):
        run = self.service.screen(self.request)
        self.assertEqual(run["status"], "awaiting_review")
        self.assertEqual(run["result"]["recommendation"], "recommend_interview")
        self.assertTrue(run["result"]["human_review_required"])
        self.assertEqual(run["result"]["assessments"][1]["status"], "not_demonstrated")
        self.assertEqual(run["result"]["follow_up_questions"][0]["criterion_id"], "aws")
        self.assertEqual(Store(self.path).get_run(run["run_id"]), run)
        self.assertEqual([event["status"] for event in run["events"]],
                         ["received", "evaluating", "validating", "awaiting_review"])
        self.assertIn("approved_at", run["role_snapshot"])

    def test_repeated_request_is_idempotent(self):
        first = self.service.screen(self.request)
        second = self.service.screen(self.request)
        self.assertEqual(first, second)
        self.assertEqual(self.provider.calls, 1)

    def test_reused_request_id_with_changed_input_conflicts(self):
        self.service.screen(self.request)
        self.request["profile_text"] += " Changed input."
        with self.assertRaises(ConflictError):
            self.service.screen(self.request)

    def test_role_versions_are_immutable(self):
        with self.assertRaises(ConflictError):
            self.service.create_role(self.role)
        self.role["role_version"] = "backend-engineer:v2"
        self.service.create_role(self.role)
        self.assertEqual(self.service.store.get_role("backend-engineer:v1")["title"], "Backend Engineer")

    def test_unapproved_or_invalid_roles_rejected(self):
        for key, value in [("approved_by", ""), ("criteria", []), ("title", "")]:
            with self.subTest(key=key):
                role = copy.deepcopy(self.role)
                role[key] = value
                with self.assertRaises(ValueError):
                    self.service.create_role(role)

    def test_missing_role_does_not_call_provider(self):
        self.request["role_version"] = "unknown"
        with self.assertRaises(KeyError):
            self.service.screen(self.request)
        self.assertEqual(self.provider.calls, 0)

    def test_input_limits(self):
        for value in ["", " ", 42, "x" * (MAX_PROFILE_CHARS + 1)]:
            with self.subTest(value_type=type(value).__name__):
                self.request["profile_text"] = value
                with self.assertRaises(ValueError):
                    self.service.screen(self.request)
        self.assertEqual(self.provider.calls, 0)

    def test_unsupported_claim_fails_without_recommendation(self):
        self.provider.change = lambda output: output["summary"][0]["evidence"][0].update(quote="AWS expert")
        run = self.service.screen(self.request)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "invalid_model_output")
        self.assertIsNone(run["result"])

    def test_model_cannot_add_a_final_decision(self):
        self.provider.change = lambda output: output.update(final_decision="hire")
        run = self.service.screen(self.request)
        self.assertEqual(run["status"], "failed")
        self.assertIsNone(run["result"])

    def test_model_cannot_invent_a_criterion(self):
        self.provider.change = lambda output: output["assessments"][0].update(criterion_id="invented")
        self.assertEqual(self.service.screen(self.request)["status"], "failed")

    def test_empty_summary_evidence_fails(self):
        self.provider.change = lambda output: output["summary"][0].update(evidence=[])
        self.assertEqual(self.service.screen(self.request)["status"], "failed")

    def test_provider_timeout_persists_failure_and_does_not_repeat(self):
        def fail(output):
            raise ProviderError("provider_unavailable")
        self.provider.change = fail
        run = self.service.screen(self.request)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["error"], "provider_unavailable")
        self.assertIsNone(run["result"])
        self.assertEqual(self.service.screen(self.request), run)
        self.assertEqual(self.provider.calls, 1)

    def test_unexpected_error_does_not_expose_profile(self):
        def fail(output):
            raise RuntimeError("private candidate data")
        self.provider.change = fail
        run = self.service.screen(self.request)
        self.assertEqual(run["error"], "processing_failed")
        self.assertNotIn("private candidate data", json.dumps(run))

    def test_demo_is_labeled_and_never_infers_a_match(self):
        self.service.provider = DemoProvider()
        run = self.service.screen(self.request)
        self.assertTrue(run["demo"])
        self.assertEqual(run["result"]["recommendation"], "needs_clarification")


if __name__ == "__main__":
    unittest.main()
