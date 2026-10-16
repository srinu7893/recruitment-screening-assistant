from collections import Counter
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from screening import operations
from screening.showcase import dataset, export_dataset, FixtureProvider, seed
from screening.storage import Store, ConflictError
from screening.build_showcase import build


class ShowcaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'test.sqlite3')

    def test_scenarios_have_valid_quotes_and_expected_routing(self):
        data = export_dataset()
        self.assertEqual(Counter(p['result']['recommendation'] for p in data['profiles']),
                         {'recommend_interview': 2, 'needs_clarification': 3, 'review_non_advancement': 1})
        for p in data['profiles']:
            self.assertEqual(len(p['result']['assessments']), 7)

    def test_seed_is_idempotent_and_demo_decisions_remain_blocked(self):
        first = seed(self.store)
        self.assertEqual(first['run_ids'], seed(self.store)['run_ids'])
        self.assertEqual(len(self.store.list_runs()), 6)
        for run in self.store.list_runs():
            self.assertTrue(run['demo'])
            for decision in ['advance', 'reject']:
                with self.assertRaises(ValueError):
                    operations.review(self.store, run['run_id'], {'revision': 0, 'decision': decision, 'reason': 'Test'}, 'reviewer')

    def test_fixture_rejects_new_input_or_changed_role(self):
        data = dataset(); p = data['profiles'][0]; provider = FixtureProvider(p)
        with self.assertRaises(ValueError):
            provider.analyze(data['role'], 'source', 'a new resume')
        role = copy.deepcopy(data['role']); role['criteria'][0]['required'] = False
        with self.assertRaises(ValueError):
            provider.analyze(role, 'source', p['profile_text'])

    def test_role_collision_does_not_load_records(self):
        role = dataset()['role']; role['criteria'][0]['required'] = False
        self.store.create_role(role)
        with self.assertRaises(ConflictError):
            seed(self.store)
        self.assertEqual(self.store.list_runs(), [])

    def test_gap_metrics_and_source_labels(self):
        seed(self.store)
        result = operations.overview(self.store)
        self.assertEqual(result['metrics']['by_source'], {'showcase': 6})
        linux = next(r for r in result['metrics']['criteria_gaps'] if r['criterion_id'] == 'linux')
        self.assertEqual((linux['meets'], linux['partial'], linux['unmet']), (4, 1, 1))
        self.assertTrue(all(r['display_name'].startswith('PS-') for r in result['runs']))

    def test_comparison_rejects_unhashable_ids(self):
        with self.assertRaises(ValueError):
            operations.compare(self.store, [{}, {}])

    def test_generated_showcase_is_current_and_contains_only_fixture_data(self):
        path = Path(__file__).resolve().parents[1] / 'showcase/index.html'
        expected = path.read_text(encoding='utf-8')
        self.assertEqual(build().read_text(encoding='utf-8'), expected)
        self.assertNotIn('__SHOWCASE_DATA__', expected)
        raw = expected.split('id="dataset">')[1].split('</script>')[0]
        self.assertEqual(json.loads(raw), export_dataset())
