import json
import unittest

import test_harness as fixtures
from harness.observation import activity


class ActivityTests(unittest.TestCase):
    def test_only_command_metadata_is_exposed(self):
        fixture = fixtures.HarnessTests()
        fixture.setUp()
        try:
            task = fixture.store.get(1)
            task['state'] = 'running'
            path = fixture.store.folder(1) / 'plan.jsonl'
            records = [
                {'type': 'item.completed', 'item': {'type': 'command_execution', 'id': 'a',
                    'command': 'cat app.py', 'aggregated_output': 'private-output-canary', 'exit_code': 0}},
                {'type': 'item.completed', 'item': {'type': 'reasoning', 'text': 'private-reasoning-canary'}}]
            path.write_text('\n'.join(map(json.dumps, records)))
            result = activity(fixture.store, task)
            self.assertEqual(result['action'], 'Изучает файлы проекта')
            self.assertEqual(result['status'], 'completed')
            self.assertNotIn('canary', json.dumps(result))
            task['state'] = 'paused'
            self.assertIsNone(activity(fixture.store, task))
        finally:
            fixture.tearDown()
