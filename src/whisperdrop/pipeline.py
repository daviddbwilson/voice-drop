"""The per-file transcription pipeline shared by the menu-bar app and the
headless watcher.

Given a queued Job, it transcribes the audio, formats Markdown, optionally runs
a light cleanup pass, and writes the transcript. When cleanup runs, the cleaned
file is canonical (``<name>.md``) and the verbatim transcript is kept alongside
as ``<name>.raw.md``.

It does NOT touch the source audio file — archiving / ledger recording is the
caller's responsibility (see watcher.finalize_success / finalize_failure).
"""

import logging
from pathlib import Path

from .cleanup import clean_to_file
from .config import Config
from .formatter import format_transcription, make_output_filename
from .transcriber import transcribe
from .watcher import Job

logger = logging.getLogger(__name__)


def process_file(job: Job, config: Config, api_key: str) -> Path:
    """Transcribe one file and write its transcript. Returns the canonical .md path.

    Raises AuthError / TranscriptionError (and other exceptions) on failure.
    """
    result = transcribe(job.path, api_key, config.transcription, config.max_retries)
    markdown = format_transcription(result, job.path.name)

    canonical = config.output_folder / make_output_filename(job.path.name)

    if not config.cleanup_enabled:
        canonical.write_text(markdown, encoding="utf-8")
        logger.info("Wrote %s", canonical.name)
        return canonical

    # Write the verbatim transcript first, then let claude write the cleaned
    # canonical file from it. If cleanup doesn't produce a valid file, promote
    # the raw transcript to canonical so there's always exactly one output.
    raw_path = canonical.with_name(f"{canonical.stem}.raw{canonical.suffix}")
    raw_path.write_text(markdown, encoding="utf-8")

    if clean_to_file(raw_path, canonical, config.cleanup_model, config.cleanup_vault):
        logger.info("Wrote %s (cleaned) + %s", canonical.name, raw_path.name)
    else:
        raw_path.replace(canonical)
        logger.info("Wrote %s (raw; cleanup skipped/failed)", canonical.name)

    return canonical
