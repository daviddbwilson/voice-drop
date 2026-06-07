"""Light-touch transcript cleanup via the headless `claude` CLI.

Raw diarized transcripts are verbose and label speakers "Speaker 0", "Speaker 1".
This runs the local `claude` CLI in print mode (no tools, pure text in/out) to do
a *very* light pass — mainly resolving speaker labels to real names when someone
clearly identifies themselves. It loads the user's ~/.claude/CLAUDE.md memory for
personal context (colleague names, etc.).

Best-effort by design: if `claude` is missing, times out, errors, or returns
something that doesn't look like a transcript, we return None and the caller keeps
the raw transcript. A missed cleanup is fine; a mangled transcript is not.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180  # seconds — generous, but we never block the watcher forever

CLEANUP_PROMPT = """\
You are lightly cleaning a voice-memo transcript. The input on stdin is a Markdown \
transcript with YAML frontmatter and diarized turns labelled "Speaker 0", "Speaker 1", etc.

Apply ONLY these changes, with a very light touch:

1. Speaker names: If — and only if — a speaker clearly identifies themselves by name \
(e.g. "Hi, I'm David", "This is Sarah speaking") or another speaker unambiguously \
addresses them by name, replace that "Speaker N" label with the person's name \
everywhere that speaker appears. You may also use names from the CLAUDE.md context \
you have been given when the match is unambiguous. If there is ANY doubt about who a \
speaker is, leave the original "Speaker N" label unchanged.

2. Leave everything else exactly as-is: do not summarise, do not remove or reword \
content, do not "fix" grammar, do not merge or reorder turns, do not change \
timestamps, and keep the frontmatter valid.

Bias strongly toward leaving things unchanged. A missed improvement is fine; a wrong \
guess — renaming the wrong speaker or inventing a name — is not.

Output ONLY the resulting Markdown document, beginning with the `---` frontmatter \
line. No preamble, no commentary, no code fences."""


def clean_transcript(
    raw_markdown: str,
    model: str,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT,
) -> str | None:
    """Return a lightly-cleaned transcript, or None to fall back to the raw one.

    Args:
        raw_markdown: The formatted transcript to clean.
        model: Model alias/name passed to `claude --model` (e.g. "sonnet").
        cwd: Directory to run from — chosen so ~/.claude/CLAUDE.md user memory loads.
        timeout: Hard wall-clock limit; on expiry we fall back to the raw transcript.
    """
    if not shutil.which("claude"):
        logger.info("claude CLI not found; skipping transcript cleanup")
        return None

    try:
        proc = subprocess.run(
            ["claude", "-p", CLEANUP_PROMPT, "--model", model],
            input=raw_markdown,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Transcript cleanup timed out after %ds; using raw transcript", timeout)
        return None
    except OSError as e:
        logger.warning("Could not run claude for cleanup (%s); using raw transcript", e)
        return None

    if proc.returncode != 0:
        logger.warning(
            "claude cleanup exited %d; using raw transcript: %s",
            proc.returncode, proc.stderr.strip()[:200],
        )
        return None

    cleaned = _strip_code_fences(proc.stdout.strip())
    if not cleaned.startswith("---"):
        logger.warning("Cleanup output didn't look like a transcript; using raw transcript")
        return None
    return cleaned


def _strip_code_fences(text: str) -> str:
    """Drop a leading/trailing ``` fence if the model wrapped its output in one."""
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    lines = lines[1:]  # drop opening ``` (possibly ```markdown)
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()
