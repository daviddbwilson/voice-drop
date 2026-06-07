"""Tests for notification helpers (no real notifications posted)."""

import unittest
from pathlib import Path
from unittest import mock

from whisperdrop import notify


class OsaStringTest(unittest.TestCase):
    def test_wraps_in_quotes(self):
        self.assertEqual(notify._osa_string("hi"), '"hi"')

    def test_escapes_double_quotes(self):
        self.assertEqual(notify._osa_string('a"b'), '"a\\"b"')

    def test_escapes_backslashes(self):
        self.assertEqual(notify._osa_string("a\\b"), '"a\\\\b"')


class TranscriptionCompleteTest(unittest.TestCase):
    def test_uses_terminal_notifier_with_reveal_when_available(self):
        def which(cmd):
            return "/usr/local/bin/terminal-notifier" if cmd == "terminal-notifier" else None

        with mock.patch.object(notify.shutil, "which", side_effect=which), \
             mock.patch.object(notify, "_run", return_value=True) as run:
            notify.transcription_complete(Path("/tmp/Foo_20260607-1430.md"))

        run.assert_called_once()
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[0], "terminal-notifier")
        self.assertIn("-execute", cmd)
        self.assertIn("open -R", cmd[cmd.index("-execute") + 1])

    def test_falls_back_to_osascript_when_terminal_notifier_missing(self):
        with mock.patch.object(notify.shutil, "which", return_value=None), \
             mock.patch.object(notify, "_run", return_value=True) as run:
            notify.transcription_complete(Path("/tmp/Foo.md"))

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][0], "osascript")

    def test_falls_back_to_osascript_when_terminal_notifier_fails(self):
        with mock.patch.object(notify.shutil, "which", return_value="/bin/terminal-notifier"), \
             mock.patch.object(notify, "_run", side_effect=[False, True]) as run:
            notify.transcription_complete(Path("/tmp/Foo.md"))

        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[0].args[0][0], "terminal-notifier")
        self.assertEqual(run.call_args_list[1].args[0][0], "osascript")


if __name__ == "__main__":
    unittest.main()
