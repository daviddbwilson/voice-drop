"""File system watcher for incoming .m4a voice memos.

Uses watchdog with macOS FSEvents for instant detection.
Handles both on_created (normal drops) and on_moved (AirDrop / browser downloads).
Debounces by waiting for file size to stabilize before queuing for transcription.
"""

import logging
import shutil
import time
from pathlib import Path
from queue import Queue
from threading import Lock, Thread

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class M4AHandler(FileSystemEventHandler):
    """Watches for new .m4a files and queues them for processing."""

    def __init__(self, queue: Queue, watch_folder: Path):
        super().__init__()
        self.queue = queue
        self.watch_folder = watch_folder
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

        # Filter: .m4a only, skip dotfiles and files in .processed/
        if path.suffix.lower() != ".m4a":
            return
        if path.name.startswith("."):
            return
        if ".processed" in path.parts or ".failed" in path.parts:
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
                    self.queue.put(path)
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
        if f.suffix.lower() == ".m4a" and not f.name.startswith("."):
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
    """Count .m4a files in .failed/."""
    failed_dir = watch_folder / ".failed"
    if not failed_dir.exists():
        return 0
    return sum(1 for f in failed_dir.iterdir()
               if f.suffix.lower() == ".m4a" and not f.name.startswith("."))


class Watcher:
    """Manages the watchdog Observer and processing loop."""

    def __init__(self, watch_folder: Path, queue: Queue):
        self.watch_folder = watch_folder
        self.queue = queue
        self.observer = Observer()
        self.handler = M4AHandler(queue, watch_folder)

    def start(self):
        """Start watching the folder (non-blocking)."""
        self.observer.schedule(self.handler, str(self.watch_folder), recursive=False)
        self.observer.daemon = True
        self.observer.start()
        logger.info("Watching: %s", self.watch_folder)

    def stop(self):
        """Stop the watcher."""
        self.observer.stop()
        self.observer.join(timeout=5)
