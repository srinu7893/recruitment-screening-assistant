"""Keep the fictional manager story consistent with the real rules engine."""
import json
from pathlib import Path
import unittest
from screening.contracts import validate_role, validate_output
from screening.rules import RulesProvider


class ManagerDemoTests(unittest.TestCase):
    def test_fictional_profiles_have_expected_evidence_and_no_automatic_qualification(self):
        fixture = json.loads((Path(__file__).resolve().parents[1]/'screening/fixtures/manager_demo.json').read_text())
        validate_role(fixture['role'])
        self.assertEqual(len({p['id'] for p in fixture['profiles']}),5)
        for profile in fixture['profiles']:
            self.assertIn('FICTIONAL DEMONSTRATION',profile['text'])
            result = validate_output(RulesProvider().analyze(fixture['role'],profile['id'],profile['text']),fixture['role'],profile['id'],profile['text'])
            self.assertEqual(sum(a['status']=='partial' for a in result['assessments']),profile['expected_mentions'],profile['id'])
            self.assertEqual(result['recommendation'],'needs_clarification')
            self.assertTrue(result['human_review_required'])


if __name__ == '__main__':
    unittest.main()
