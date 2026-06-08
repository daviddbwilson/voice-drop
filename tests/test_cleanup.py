"""Tests for the headless-claude transcript cleanup (no real CLI calls)."""

import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from whisperdrop import cleanup

FRONTMATTER = "---\ntitle: x\n---\n\n# x\n\n**David** (0:01)\nhello\n"


class LooksLikeTranscriptTest(unittest.TestCase):
    def test_true_for_frontmatter(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("\n  " + FRONTMATTER, encoding="utf-8")
            self.assertTrue(cleanup._looks_like_transcript(p))

    def test_false_for_prose(self):
        with TemporaryDirectory() as d:
            p = Path(d) / "x.md"
            p.write_text("Sure, here is the transcript.", encoding="utf-8")
            self.assertFalse(cleanup._looks_like_transcript(p))

    def test_false_for_missing_file(self):
        self.assertFalse(cleanup._looks_like_transcript(Path("/no/such/file.md")))


class CleanToFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.raw = self.dir / "memo.raw.md"
        self.raw.write_text(FRONTMATTER, encoding="utf-8")
        self.out = self.dir / "memo.md"

    def tearDown(self):
        self._tmp.cleanup()

    def _run_writing(self, content, returncode=0):
        """A fake subprocess.run that simulates claude writing self.out."""
        def _run(cmd, **kwargs):
            if content is not None:
                self.out.write_text(content, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, returncode, "", "boom")
        return _run

    def test_returns_false_when_cli_missing(self):
        with mock.patch.object(cleanup.shutil, "which", return_value=None):
            self.assertFalse(cleanup.clean_to_file(self.raw, self.out, "sonnet"))

    def test_success_writes_valid_file(self):
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", side_effect=self._run_writing(FRONTMATTER)):
            self.assertTrue(cleanup.clean_to_file(self.raw, self.out, "sonnet"))
        self.assertTrue(self.out.exists())

    def test_invalid_output_is_discarded(self):
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", side_effect=self._run_writing("oops no frontmatter")):
            self.assertFalse(cleanup.clean_to_file(self.raw, self.out, "sonnet"))
        self.assertFalse(self.out.exists())  # garbage cleaned up

    def test_nonzero_exit_discards_output(self):
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", side_effect=self._run_writing(FRONTMATTER, returncode=1)):
            self.assertFalse(cleanup.clean_to_file(self.raw, self.out, "sonnet"))
        self.assertFalse(self.out.exists())

    def test_timeout_returns_false(self):
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
            self.assertFalse(cleanup.clean_to_file(self.raw, self.out, "sonnet"))

    def _capture_cmd(self, vault):
        captured = {}

        def _run(cmd, **kwargs):
            captured["cmd"] = cmd
            self.out.write_text(FRONTMATTER, encoding="utf-8")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", side_effect=_run):
            cleanup.clean_to_file(self.raw, self.out, "sonnet", vault=vault)
        return captured["cmd"]

    def test_command_always_allows_read_and_write_tools(self):
        cmd = self._capture_cmd(None)
        self.assertIn("--allowedTools", cmd)
        self.assertEqual(cmd[cmd.index("--allowedTools") + 1], "Read,Glob,Grep,Write")
        # Output folder is always granted; with no vault there's a single --add-dir.
        self.assertEqual(cmd.count("--add-dir"), 1)
        self.assertEqual(cmd[cmd.index("--add-dir") + 1], str(self.dir))

    def test_vault_dir_is_granted_read_access(self):
        with TemporaryDirectory() as vault:
            cmd = self._capture_cmd(Path(vault))
            self.assertEqual(cmd.count("--add-dir"), 2)
            self.assertIn(str(Path(vault)), cmd)

    def test_missing_vault_is_not_granted(self):
        cmd = self._capture_cmd(Path("/no/such/vault"))
        self.assertEqual(cmd.count("--add-dir"), 1)


if __name__ == "__main__":
    unittest.main()
