import os
import tempfile
import unittest
from pathlib import Path

from harness.security import read_regular, regular_files, tree_entries


class SafeSourceReadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.root = self.base / 'workspace'
        self.root.mkdir()
        (self.base / 'outside.txt').write_text('harmless outside canary')

    def tearDown(self):
        self.temporary.cleanup()

    def test_file_replaced_after_listing_cannot_follow_symlink(self):
        path = self.root / 'app.py'
        path.write_text('normal')
        listed = dict(regular_files(self.root))
        path.unlink()
        path.symlink_to(self.base / 'outside.txt')
        with self.assertRaises(OSError):
            read_regular(self.root, next(iter(listed)))

    def test_directory_replaced_during_walk_is_not_followed(self):
        folder = self.root / 'sub'
        folder.mkdir()
        (folder / 'app.py').write_text('normal')
        entries = tree_entries(self.root)
        self.assertEqual(next(entries)[0], 'sub')
        folder.rename(self.root / 'original')
        folder.symlink_to(self.base, target_is_directory=True)
        with self.assertRaises(OSError):
            list(entries)

    def test_hardlink_and_fifo_are_rejected_without_reading(self):
        os.link(self.base / 'outside.txt', self.root / 'alias')
        os.mkfifo(self.root / 'pipe')
        for name in ('alias', 'pipe'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    read_regular(self.root, name)

    def test_protected_paths_are_rejected_and_regular_mode_is_preserved(self):
        path = self.root / 'app.py'
        path.write_text('normal')
        path.chmod(0o755)
        content, info = read_regular(self.root, 'app.py', with_stat=True)
        self.assertEqual(content, b'normal')
        self.assertTrue(info.st_mode & 0o111)
        for name in ('.env', '../outside.txt', str(self.base / 'outside.txt')):
            with self.assertRaises(ValueError):
                read_regular(self.root, name)
