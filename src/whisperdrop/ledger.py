"""Persistent record of already-transcribed files.

Folders watched "in place" (e.g. ~/Downloads) don't move their originals to
.processed/, so the move-to-archive trick that dedupes the primary folder
doesn't apply. Instead we remember which paths we've already transcribed in a
small JSON file, keyed by absolute path. This survives restarts so a file left
sitting in Downloads isn't transcribed again on the next launch.
"""

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Iterable

logger = logging.getLogger(__name__)


class Ledger:
    """A thread-safe, persistent set of processed file paths."""

    def __init__(self, path: Path):
        self._path = path
        self._lock = Lock()
        self._seen: set[str] = self._load()

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return set(data.get("processed", []))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read ledger %s (%s); starting empty", self._path, e)
            return set()

    @staticmethod
    def _key(path: Path) -> str:
        return str(path.resolve())

    def seen(self, path: Path) -> bool:
        with self._lock:
            return self._key(path) in self._seen

    def add(self, path: Path) -> None:
        with self._lock:
            self._seen.add(self._key(path))
            self._flush()

    def seed(self, paths: Iterable[Path]) -> None:
        """Mark a batch of paths as already-seen (used to skip the startup backlog)."""
        with self._lock:
            before = len(self._seen)
            self._seen.update(self._key(p) for p in paths)
            if len(self._seen) != before:
                self._flush()

    def _flush(self) -> None:
        """Write the ledger atomically (caller holds the lock)."""
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps({"processed": sorted(self._seen)}),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as e:
            logger.warning("Could not write ledger %s: %s", self._path, e)
            tmp.unlink(missing_ok=True)
