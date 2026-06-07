"""Tests for the headless-claude transcript cleanup (no real CLI calls)."""

import subprocess
import unittest
from pathlib import Path
from unittest import mock

from whisperdrop import cleanup

FRONTMATTER = "---\ntitle: x\n---\n\n# x\n\n**David** (0:01)\nhello\n"


class StripFencesTest(unittest.TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(cleanup._strip_code_fences("---\nhi"), "---\nhi")

    def test_strips_markdown_fence(self):
        text = "```markdown\n---\nhi\n```"
        self.assertEqual(cleanup._strip_code_fences(text), "---\nhi")

    def test_strips_bare_fence(self):
        text = "```\n---\nhi\n```"
        self.assertEqual(cleanup._strip_code_fences(text), "---\nhi")


class CleanTranscriptTest(unittest.TestCase):
    def test_returns_none_when_cli_missing(self):
        with mock.patch.object(cleanup.shutil, "which", return_value=None):
            self.assertIsNone(cleanup.clean_transcript("raw", "sonnet", Path(".")))

    def test_returns_cleaned_on_success(self):
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout=FRONTMATTER, stderr="")
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", return_value=completed):
            self.assertEqual(cleanup.clean_transcript("raw", "sonnet", Path(".")), FRONTMATTER.strip())

    def test_rejects_non_transcript_output(self):
        completed = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="Sure! Here is the cleaned transcript.", stderr="",
        )
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", return_value=completed):
            self.assertIsNone(cleanup.clean_transcript("raw", "sonnet", Path(".")))

    def test_returns_none_on_nonzero_exit(self):
        completed = subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run", return_value=completed):
            self.assertIsNone(cleanup.clean_transcript("raw", "sonnet", Path(".")))

    def test_returns_none_on_timeout(self):
        with mock.patch.object(cleanup.shutil, "which", return_value="/usr/bin/claude"), \
             mock.patch.object(cleanup.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)):
            self.assertIsNone(cleanup.clean_transcript("raw", "sonnet", Path(".")))


if __name__ == "__main__":
    unittest.main()
