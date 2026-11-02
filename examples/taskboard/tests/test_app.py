import contextlib
import io
import json
import unittest
import uuid
from pathlib import Path

import app


class TaskboardTests(unittest.TestCase):
    def setUp(self):
        self.store = Path.cwd() / f"taskboard-test-{uuid.uuid4().hex}.json"

    def tearDown(self):
        self.store.unlink(missing_ok=True)

    def test_empty_list(self):
        self.assertEqual(app.list_tasks(self.store), [])

    def test_add_trims_title_and_assigns_ids(self):
        first = app.add_task(self.store, "  Купить молоко  ")
        second = app.add_task(self.store, "Написать тесты")
        self.assertEqual(first, {"id": 1, "title": "Купить молоко", "done": False})
        self.assertEqual(second["id"], 2)
        self.assertEqual(len(app.list_tasks(self.store)), 2)

    def test_empty_title_is_rejected(self):
        with self.assertRaises(ValueError):
            app.add_task(self.store, "  ")
        self.assertFalse(self.store.exists())

    def test_complete_preserves_other_tasks(self):
        app.add_task(self.store, "Первая")
        app.add_task(self.store, "Вторая")
        self.assertTrue(app.complete_task(self.store, 1)["done"])
        self.assertFalse(app.list_tasks(self.store)[1]["done"])

    def test_unknown_id_is_rejected(self):
        with self.assertRaises(ValueError):
            app.complete_task(self.store, 99)

    def test_repeat_complete_is_idempotent(self):
        app.add_task(self.store, "Первая")
        app.complete_task(self.store, 1)
        app.complete_task(self.store, 1)
        self.assertEqual(len(app.list_tasks(self.store)), 1)

    def test_cli_returns_json(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            app.main(["--store", str(self.store), "add", "Проверить CLI"])
        self.assertEqual(json.loads(output.getvalue())["id"], 1)
        with contextlib.redirect_stdout(io.StringIO()) as output:
            app.main(["--store", str(self.store), "list"])
        self.assertEqual(len(json.loads(output.getvalue())), 1)


if __name__ == "__main__":
    unittest.main()
