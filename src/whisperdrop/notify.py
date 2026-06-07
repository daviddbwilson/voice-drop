"""macOS notifications for completed transcripts.

Works from both the menu-bar app and the headless LaunchAgent. If
`terminal-notifier` is installed, the notification reveals the transcript in
Finder when clicked; otherwise we fall back to a plain `osascript` notification
(which can't carry a click action).
"""

import logging
import shlex
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TITLE = "Whisper Drop"


def transcription_complete(output_path: Path) -> None:
    """Notify that a transcript is ready, revealing it in Finder if possible."""
    message = f"Transcript ready: {output_path.name}"

    if shutil.which("terminal-notifier"):
        # -execute runs the command when the notification is clicked.
        reveal = f"open -R {shlex.quote(str(output_path))}"
        if _run(["terminal-notifier", "-title", TITLE, "-message", message, "-execute", reveal]):
            return
        # fall through to osascript if terminal-notifier failed

    script = f"display notification {_osa_string(message)} with title {_osa_string(TITLE)}"
    _run(["osascript", "-e", script])


def _run(cmd: list[str]) -> bool:
    """Run a notification command; never raise. Returns True on success."""
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError) as e:
        logger.warning("Could not post notification via %s: %s", cmd[0], e)
        return False


def _osa_string(s: str) -> str:
    """Quote a Python string as an AppleScript string literal."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
