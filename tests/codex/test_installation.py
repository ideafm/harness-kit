import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.installation import install, diagnose
from harness.service import KIT


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary.name).resolve() / 'bin with spaces'
        self.folder.mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_install_is_repeatable_and_uses_current_controller(self):
        with patch.dict(os.environ, {'PATH': str(self.folder)}):
            result = install(self.folder)
            self.assertTrue(result['on_path'])
            self.assertEqual(install(self.folder), result)
        for name in ('tw', 'tw-web'):
            self.assertEqual(os.readlink(self.folder / name), str(KIT / 'bin' / name))

    def test_foreign_file_is_preserved_without_partial_install(self):
        (self.folder / 'tw-web').write_text('foreign')
        with self.assertRaises(ValueError):
            install(self.folder)
        self.assertEqual((self.folder / 'tw-web').read_text(), 'foreign')
        self.assertFalse((self.folder / 'tw').exists())

    def test_symlinked_directory_and_hidden_destination_fail_closed(self):
        alias = self.folder.parent / 'alias'
        alias.symlink_to(self.folder, target_is_directory=True)
        for path in (alias, self.folder / '.hidden'):
            with self.subTest(path=path):
                with self.assertRaises((OSError, ValueError)):
                    install(path)
        self.assertEqual(list(self.folder.iterdir()), [])

    def test_diagnose_does_not_call_model_or_require_project(self):
        with patch('harness.installation.doctor') as probe:
            self.assertIn('python', diagnose())
            probe.assert_not_called()
        with patch('harness.installation.shutil.which', return_value='/usr/bin/codex'), \
                patch('harness.installation.doctor', return_value='canary passed') as probe:
            self.assertEqual(diagnose(True)['sandbox'], 'canary passed')
            probe.assert_called_once_with('/usr/bin/codex')
