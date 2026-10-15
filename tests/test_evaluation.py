import unittest
from screening.evaluation import evaluate_provider
from screening.showcase import dataset, FixtureProvider


class EvaluationTests(unittest.TestCase):
    def test_fixture_agreement_and_invalid_outputs_are_separate(self):
        class Provider:
            name='test';model='test'
            def analyze(self, role, source_id, profile):
                p=next(p for p in dataset()['profiles'] if p['id']==source_id)
                if source_id=='PS-106':
                    raise ValueError('private provider detail')
                return FixtureProvider(p).analyze(role, source_id, profile)
        result=evaluate_provider(Provider())
        self.assertEqual(result['valid_outputs'],5)
        self.assertEqual(result['criteria_compared'],35)
        self.assertEqual(result['criterion_agreement'],1)
        self.assertNotIn('private provider detail',str(result))
