"""Tests for the persistent processed-file ledger."""

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from whisperdrop.ledger import Ledger


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.path = self.dir / "processed.json"

    def tearDown(self):
        self._tmp.cleanup()

    def test_add_and_seen(self):
        ledger = Ledger(self.path)
        f = self.dir / "memo.m4a"
        self.assertFalse(ledger.seen(f))
        ledger.add(f)
        self.assertTrue(ledger.seen(f))

    def test_persists_across_instances(self):
        f = self.dir / "memo.m4a"
        Ledger(self.path).add(f)
        # A fresh instance should load the prior state from disk.
        self.assertTrue(Ledger(self.path).seen(f))

    def test_seed_marks_batch_seen(self):
        files = [self.dir / "a.m4a", self.dir / "b.m4a"]
        ledger = Ledger(self.path)
        ledger.seed(files)
        for f in files:
            self.assertTrue(ledger.seen(f))

    def test_seen_is_keyed_by_resolved_path(self):
        ledger = Ledger(self.path)
        ledger.add(self.dir / "sub" / ".." / "memo.m4a")
        self.assertTrue(ledger.seen(self.dir / "memo.m4a"))

    def test_corrupt_file_starts_empty(self):
        self.path.write_text("{not valid json", encoding="utf-8")
        ledger = Ledger(self.path)
        self.assertFalse(ledger.seen(self.dir / "memo.m4a"))
        # ...and the ledger still works after recovering.
        ledger.add(self.dir / "memo.m4a")
        self.assertTrue(ledger.seen(self.dir / "memo.m4a"))

    def test_written_file_is_valid_json(self):
        ledger = Ledger(self.path)
        ledger.add(self.dir / "memo.m4a")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIn("processed", data)
        self.assertEqual(len(data["processed"]), 1)


if __name__ == "__main__":
    unittest.main()
