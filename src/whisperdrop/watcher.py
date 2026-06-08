"""File system watcher for incoming voice memos.

Uses watchdog with macOS FSEvents for instant detection.
Handles both on_created (normal drops) and on_moved (AirDrop / browser downloads).
Debounces by waiting for file size to stabilize before queuing for transcription.

A watched folder is either "archive" (the primary ~/VoiceDrop folder — originals
move to .processed/ once done) or "in place" (e.g. ~/Downloads — originals stay
put and dedup is handled by the persistent Ledger instead).
"""

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from threading import Lock, Thread

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .ledger import Ledger
from .transcriber import SUPPORTED_FORMATS

logger = logging.getLogger(__name__)

# Supported audio extensions for the primary folder — derived from the
# transcriber's format table so the two can't drift apart.
SUPPORTED_EXTENSIONS = frozenset(SUPPORTED_FORMATS)


@dataclass(frozen=True)
class WatchFolder:
    """A folder to watch and how to treat its files once transcribed."""

    path: Path
    extensions: frozenset[str]
    archive: bool  # True: move original to .processed/. False: leave in place.


@dataclass(frozen=True)
class Job:
    """One file queued for transcription, tagged with the folder it came from."""

    path: Path
    source: WatchFolder


class AudioHandler(FileSystemEventHandler):
    """Watches one folder for new audio files and queues them for processing."""

    def __init__(self, queue: Queue, source: WatchFolder, ledger: Ledger | None = None):
        super().__init__()
        self.queue = queue
        self.source = source
        self.ledger = ledger
        # Dedupe: tracks files currently being debounced/queued so
        # duplicate events (e.g. create + move for same file) don't
        # cause double transcriptions.
        self._pending: set[Path] = set()
        self._pending_lock = Lock()

    def on_created(self, event: FileSystemEvent):
        self._handle(event.src_path)

    def on_moved(self, event: FileSystemEvent):
        # AirDrop and browser downloads move files into the folder
        self._handle(event.dest_path)

    def _handle(self, path_str: str):
        path = Path(path_str)

        # Filter: this folder's formats only, skip dotfiles and files in .processed/
        if path.suffix.lower() not in self.source.extensions:
            return
        if path.name.startswith("."):
            return
        if ".processed" in path.parts or ".failed" in path.parts:
            return
        # In-place folders: skip anything we've already transcribed.
        if self.ledger is not None and self.ledger.seen(path):
            logger.debug("Already transcribed, skipping: %s", path.name)
            return

        # Dedupe: skip if we're already waiting on this file
        with self._pending_lock:
            if path in self._pending:
                logger.debug("Skipping duplicate event for: %s", path.name)
                return
            self._pending.add(path)

        logger.info("Detected new file: %s", path.name)

        # Debounce: wait for file size to stabilize (handles partial writes)
        Thread(target=self._wait_and_queue, args=(path,), daemon=True).start()

    def _wait_and_queue(self, path: Path):
        """Wait until the file size stops changing, then queue it."""
        try:
            prev_size = -1
            for _ in range(60):  # Max 60 seconds waiting
                if not path.exists():
                    logger.warning("File disappeared before processing: %s", path.name)
                    return
                curr_size = path.stat().st_size
                if curr_size > 0 and curr_size == prev_size:
                    # Size stable — file write is complete
                    self.queue.put(Job(path, self.source))
                    logger.info("Queued for transcription: %s", path.name)
                    return
                prev_size = curr_size
                time.sleep(1)
            logger.warning("Timed out waiting for file to stabilize: %s", path.name)
        except Exception:
            logger.exception("Error waiting for file: %s", path.name)
        finally:
            with self._pending_lock:
                self._pending.discard(path)


def archive_file(path: Path, watch_folder: Path) -> Path:
    """Move a processed file to watch_folder/.processed/"""
    archive_dir = watch_folder / ".processed"
    archive_dir.mkdir(exist_ok=True)
    dest = archive_dir / path.name
    # Handle name collision in archive
    if dest.exists():
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while dest.exists():
            dest = archive_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    shutil.move(str(path), str(dest))
    logger.info("Archived: %s → .processed/%s", path.name, dest.name)
    return dest


def quarantine_file(path: Path, watch_folder: Path) -> Path:
    """Move a failed file to watch_folder/.failed/ for later retry."""
    failed_dir = watch_folder / ".failed"
    failed_dir.mkdir(exist_ok=True)
    dest = failed_dir / path.name
    if dest.exists():
        stem = path.stem
        suffix = path.suffix
        counter = 1
        while dest.exists():
            dest = failed_dir / f"{stem}_{counter}{suffix}"
            counter += 1
    shutil.move(str(path), str(dest))
    logger.info("Quarantined: %s → .failed/%s", path.name, dest.name)
    return dest


def retry_failed(watch_folder: Path) -> int:
    """Move all files from .failed/ back to the watch folder for reprocessing.

    Returns the number of files moved.
    """
    failed_dir = watch_folder / ".failed"
    if not failed_dir.exists():
        return 0
    count = 0
    for f in failed_dir.iterdir():
        if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("."):
            dest = watch_folder / f.name
            # Avoid overwriting an existing file in the watch folder
            if dest.exists():
                stem = f.stem
                suffix = f.suffix
                counter = 1
                while dest.exists():
                    dest = watch_folder / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.move(str(f), str(dest))
            logger.info("Retrying: .failed/%s → %s", f.name, dest.name)
            count += 1
    return count


def count_failed(watch_folder: Path) -> int:
    """Count audio files in .failed/."""
    failed_dir = watch_folder / ".failed"
    if not failed_dir.exists():
        return 0
    return sum(1 for f in failed_dir.iterdir()
               if f.suffix.lower() in SUPPORTED_EXTENSIONS and not f.name.startswith("."))


def build_watch_folders(config) -> list[WatchFolder]:
    """Derive the list of folders to watch from config.

    The primary watch_folder archives originals; extra folders are watched in
    place with a narrower extension set.
    """
    folders = [WatchFolder(config.watch_folder, SUPPORTED_EXTENSIONS, archive=True)]
    for extra in config.extra_watch_folders:
        folders.append(WatchFolder(extra, config.extra_watch_extensions, archive=False))
    return folders


def existing_audio(folder: WatchFolder) -> list[Path]:
    """List the audio files already present in a watched folder."""
    found: set[Path] = set()
    for ext in folder.extensions:
        found.update(folder.path.glob(f"*{ext}"))
    return sorted(p for p in found if not p.name.startswith("."))


def prime_queue(folders: list[WatchFolder], queue: Queue, ledger: Ledger) -> None:
    """Handle files already present at startup.

    Archive folders: queue the backlog for transcription (as before).
    In-place folders: seed the ledger so the existing backlog is left untouched
    and only newly-arriving files get transcribed.
    """
    for folder in folders:
        files = existing_audio(folder)
        if folder.archive:
            for path in files:
                logger.info("Found existing file: %s", path.name)
                queue.put(Job(path, folder))
        else:
            ledger.seed(files)
            logger.info("Seeded %d existing file(s) in %s as already-seen", len(files), folder.path)


def finalize_success(job: Job, ledger: Ledger) -> None:
    """Mark a successfully-transcribed source file as done."""
    if job.source.archive:
        archive_file(job.path, job.source.path)
    else:
        ledger.add(job.path)


def finalize_failure(job: Job) -> None:
    """Handle a failed source file.

    Archive folders quarantine the original to .failed/ for retry. In-place
    folders leave the original where it is (and out of the ledger, so a fresh
    event can retry it) — we just log.
    """
    if job.source.archive:
        quarantine_file(job.path, job.source.path)
    else:
        logger.warning("Leaving failed in-place file untouched: %s", job.path)


class Watcher:
    """Manages the watchdog Observer across one or more watched folders."""

    def __init__(self, folders: list[WatchFolder], queue: Queue, ledger: Ledger | None = None):
        self.folders = folders
        self.queue = queue
        self.ledger = ledger
        self.observer = Observer()

    def start(self):
        """Start watching all folders (non-blocking)."""
        for folder in self.folders:
            if not folder.path.is_dir():
                logger.warning("Watch folder does not exist, skipping: %s", folder.path)
                continue
            # The ledger only governs in-place folders; archive folders dedup via the move.
            ledger = self.ledger if not folder.archive else None
            handler = AudioHandler(self.queue, folder, ledger)
            self.observer.schedule(handler, str(folder.path), recursive=False)
            logger.info("Watching: %s (%s)", folder.path, "archive" if folder.archive else "in place")
        self.observer.daemon = True
        self.observer.start()

    def stop(self):
        """Stop the watcher."""
        self.observer.stop()
        self.observer.join(timeout=5)
