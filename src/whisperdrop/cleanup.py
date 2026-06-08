"""Light-touch transcript cleanup via the headless `claude` CLI.

Raw diarized transcripts are verbose and label speakers "Speaker 0", "Speaker 1".
This runs the local `claude` CLI in print mode to do a *very* light pass — mainly
resolving speaker labels to real names when someone clearly identifies themselves,
plus a feather-light grammar / obvious-mis-transcription touch-up. It loads the
user's ~/.claude/CLAUDE.md memory and, if granted, reads an Obsidian vault for
personal context (colleague names, project terms, etc.).

claude writes the cleaned file itself (Write tool) rather than streaming it over
stdout, so there's no output to parse. It's granted only read-only vault access
plus Read/Write — anything else is denied (not prompted), so the call stays
non-interactive, and a hard wall-clock timeout backstops it regardless.

Best-effort by design: if `claude` is missing, times out, errors, or doesn't
produce a valid transcript file, we return False and the caller keeps the raw
transcript. A missed cleanup is fine; a mangled or missing transcript is not.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 180  # seconds — generous, but we never block the watcher forever

# Read/Glob/Grep let it consult the vault; Write lets it save the result itself.
ALLOWED_TOOLS = "Read,Glob,Grep,Write"

_RULES = """\
1. Speaker names: If — and only if — a speaker clearly identifies themselves by name \
(e.g. "Hi, I'm David", "This is Sarah speaking") or another speaker unambiguously \
addresses them by name, replace that "Speaker N" label with the person's name \
everywhere that speaker appears. If there is ANY doubt about who a speaker is, leave \
the original "Speaker N" label unchanged.

2. Merge consecutive turns from the SAME speaker into one turn: concatenate their \
text in order and keep the timestamp of the first turn in the run. Never merge across \
a change of speaker, and never reorder turns. (This is the main thing that de-clutters \
the transcript — diarization tends to split one person's speech into many tiny turns.)

3. Do an extremely light-touch pass on grammar and extremely probable transcription \
errors. However, when even in the slightest reasonable doubt, bias strongly toward \
leaving things unchanged. A missed improvement is fine; a wrong guess — renaming the \
wrong speaker, inventing a name, or switching an unfamiliar but correct term to an \
incorrect one — is not. Do not summarise, do not drop spoken content, do not invent \
timestamps, and keep the frontmatter valid.

You may use names/context from the CLAUDE.md context you have as well as from the \
Obsidian vault (in ~/vault) if you have been given read access to it."""


def _prompt(raw_path: Path, out_path: Path) -> str:
    return (
        f"You are lightly cleaning a voice-memo transcript. Read the transcript at "
        f"{raw_path} — it is Markdown with YAML frontmatter and diarized turns "
        f'labelled "Speaker 0", "Speaker 1", etc.\n\n'
        f"{_RULES}\n\n"
        f"Write the resulting Markdown document to {out_path}, beginning with the "
        f"`---` frontmatter line. Write that one file only — create no other files "
        f"and print nothing to stdout."
    )


def clean_to_file(
    raw_path: Path,
    out_path: Path,
    model: str,
    vault: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> bool:
    """Have headless claude write a lightly-cleaned ``out_path`` from ``raw_path``.

    Returns True if a valid cleaned transcript file was written; False if cleanup
    is unavailable or failed (the caller should fall back to the raw transcript).

    Args:
        raw_path: The verbatim transcript to clean (already on disk).
        out_path: Where the cleaned transcript should be written.
        model: Model alias/name passed to `claude --model` (e.g. "sonnet").
        vault: If given and a directory, granted read-only so the model can resolve
            names from an Obsidian vault.
        timeout: Hard wall-clock limit; on expiry we fall back to the raw transcript.
    """
    if not shutil.which("claude"):
        logger.info("claude CLI not found; skipping transcript cleanup")
        return False

    cmd = [
        "claude", "-p", _prompt(raw_path, out_path),
        "--model", model,
        "--allowedTools", ALLOWED_TOOLS,
        "--add-dir", str(out_path.parent),
    ]
    if vault is not None and vault.is_dir():
        cmd += ["--add-dir", str(vault)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(out_path.parent),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Transcript cleanup timed out after %ds; using raw transcript", timeout)
        return _fail(out_path)
    except OSError as e:
        logger.warning("Could not run claude for cleanup (%s); using raw transcript", e)
        return False

    if proc.returncode != 0:
        logger.warning(
            "claude cleanup exited %d; using raw transcript: %s",
            proc.returncode, proc.stderr.strip()[:200],
        )
        return _fail(out_path)

    if not _looks_like_transcript(out_path):
        logger.warning("Cleanup did not produce a valid transcript; using raw transcript")
        return _fail(out_path)

    return True


def _fail(out_path: Path) -> bool:
    """Discard any partial/garbage output so the caller can promote the raw file."""
    out_path.unlink(missing_ok=True)
    return False


def _looks_like_transcript(path: Path) -> bool:
    """A valid transcript starts with the `---` YAML frontmatter line."""
    try:
        return path.read_text(encoding="utf-8").lstrip().startswith("---")
    except OSError:
        return False
