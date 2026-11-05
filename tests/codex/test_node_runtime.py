import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness.node import prepared_toolchain, tree_hash
from harness.state import atomic_json


class PreparedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.home = Path(self.temporary.name) / 'project/.harness/toolchains/next-ui'
        self.runtime = self.home / 'runtime/node'
        self.dependencies = self.home / 'dependencies/node_modules'
        self.runtime.parent.mkdir(parents=True)
        self.runtime.write_text('prepared binary')
        (self.runtime.parent / 'library.dylib').write_text('prepared library')
        self.dependencies.mkdir(parents=True)
        (self.dependencies / 'package.js').write_text('prepared package')
        self.data = {'prepared_node': str(self.runtime), 'dependencies': str(self.dependencies),
                     'runtime_sha256': tree_hash(self.runtime.parent),
                     'dependencies_sha256': tree_hash(self.dependencies)}
        atomic_json(self.home / 'toolchain.json', self.data)

    def tearDown(self):
        self.temporary.cleanup()

    def test_prepared_runtime_survives_removal_of_original_node(self):
        with patch('harness.node.NODE', Path(self.temporary.name) / 'removed-node'), \
                patch('harness.node.runtime_files', side_effect=AssertionError('source runtime must not be used')):
            self.assertEqual(prepared_toolchain(self.home), self.data)

    def test_tampered_binary_library_and_dependencies_fail_closed(self):
        for path in (self.runtime, self.runtime.parent / 'library.dylib', self.dependencies / 'package.js'):
            with self.subTest(path=path.name):
                original = path.read_text()
                path.write_text('changed')
                with self.assertRaises(RuntimeError):
                    prepared_toolchain(self.home)
                path.write_text(original)

    def test_receipt_cannot_redirect_runtime_or_dependencies(self):
        for key in ('prepared_node', 'dependencies'):
            with self.subTest(key=key):
                data = dict(self.data)
                data[key] = str(Path(self.temporary.name) / 'outside')
                atomic_json(self.home / 'toolchain.json', data)
                with self.assertRaises(RuntimeError):
                    prepared_toolchain(self.home)

    def test_symlinked_runtime_and_receipt_are_rejected(self):
        for path in (self.runtime, self.runtime.parent / 'library.dylib', self.home / 'toolchain.json'):
            with self.subTest(path=path.name):
                content = path.read_bytes()
                target = Path(self.temporary.name) / 'target'
                target.write_bytes(content)
                path.unlink()
                path.symlink_to(target)
                with self.assertRaises(RuntimeError):
                    prepared_toolchain(self.home)
                path.unlink()
                path.write_bytes(content)
