import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock

from harness.attachment_view import image_view
from harness.gemini import Gemini
import test_harness as fixtures


class GeminiImageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'image.png'
        self.source.write_bytes(b'\x89PNG\r\n\x1a\nfixture')
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        (self.workspace / 'app.py').write_text('value=1')
        self.folder = self.root / 'task'
        self.folder.mkdir()
        self.config = {'agy': '/usr/bin/agy', 'timeout': 30, 'attachment_images': [str(self.source)]}

    def tearDown(self):
        self.temporary.cleanup()

    def test_view_is_isolated_and_removed_on_error(self):
        with self.assertRaisesRegex(RuntimeError, 'cancelled'):
            with image_view([str(self.source)]) as (folder, records):
                view = folder
                self.assertEqual(len(list(folder.iterdir())), 1)
                self.assertEqual(Path(records[0]['path']).read_bytes(), self.source.read_bytes())
                self.assertNotEqual(folder, self.source.parent)
                raise RuntimeError('cancelled')
        self.assertFalse(view.exists())
        self.assertTrue(self.source.exists())

    def test_mutation_is_rejected_and_original_preserved(self):
        original = self.source.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'изменено'):
            with image_view([str(self.source)]) as (folder, records):
                path = Path(records[0]['path'])
                path.chmod(0o600)
                path.write_bytes(b'modified')
        self.assertFalse(folder.exists())
        self.assertEqual(self.source.read_bytes(), original)

    def test_symlink_source_is_rejected(self):
        alias = self.root / 'alias.png'
        alias.symlink_to(self.source)
        with self.assertRaises(OSError):
            with image_view([str(alias)]):
                self.fail('symlink accepted')

    def test_transport_uses_task_view_and_preserves_write_denials(self):
        expected = fixtures.response()
        paths = []
        def execute(command, cwd, output, timeout, interrupted, input_text, env):
            directory = Path(command[command.index('--add-dir') + 1])
            paths.append(directory)
            settings = json.loads(command[command.index('--settings') + 1])
            self.assertIn(f'write_file({directory}/**)', settings['permissions']['deny'])
            self.assertIn('command(*)', settings['permissions']['deny'])
            prompt = json.loads(input_text)['message']['content']
            self.assertIn(str(directory / 'image-1.png'), prompt)
            self.assertIn('view_file', prompt)
            self.assertIn('read-only', prompt)
            self.assertNotIn(str(self.source), prompt)
            self.assertEqual(len(list(directory.iterdir())), 1)
            (self.folder / 'implement.response.json').write_text(json.dumps(expected))
            return 0
        with patch('harness.gemini.resolve_agy', return_value='/usr/bin/agy'), patch('harness.gemini.subprocess.run', return_value=Mock(returncode=0, stdout='1.5.5 --add-dir', stderr='')), patch('harness.gemini.execute', side_effect=execute):
            actual = Gemini(self.config).call('implement', self.workspace, self.folder, 'task', lambda: False, allowed_files=['app.py'])
        self.assertEqual(actual, expected)
        self.assertFalse(paths[0].exists())
        self.assertEqual(sorted(path.name for path in self.workspace.iterdir()), ['app.py'])

    def test_sdk_does_not_silently_drop_images(self):
        with self.assertRaisesRegex(RuntimeError, 'SDK multimodal'):
            Gemini({**self.config, 'gemini_mode': 'sdk'}).call('plan', self.workspace, self.folder, 'task', lambda: False)
