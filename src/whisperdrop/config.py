"""Configuration management via TOML file.

Loads settings from ~/.config/whisperdrop/config.toml, creating it with
sensible defaults if it doesn't exist. All paths are expanded (~ → /Users/...).
Folders are created automatically if missing.
"""

import tomllib
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "whisperdrop"
CONFIG_FILE = CONFIG_DIR / "config.toml"

DEFAULTS = {
    "paths": {
        "watch_folder": "~/VoiceDrop",
        "output_folder": "~/VoiceDrop/Transcripts",
        # Folders watched in addition to watch_folder. Files here are
        # transcribed in place and never moved (see watcher.WatchFolder).
        "extra_watch_folders": ["~/Downloads"],
        # Extensions picked up from extra_watch_folders (a narrower set than
        # the primary folder, since Downloads holds lots of unrelated audio).
        "extra_watch_extensions": [".m4a", ".qta"],
    },
    "transcription": {
        "model": "nova-3",
        "language": "en",
        "diarize": True,
        "smart_format": True,
        "paragraphs": True,
        "utterances": True,
    },
    "cleanup": {
        # Light-touch transcript cleanup via the headless `claude` CLI.
        "enabled": True,
        "model": "sonnet",
    },
    "behavior": {
        "notification_on_complete": True,
        "max_retries": 3,
    },
}

DEFAULT_TOML = """\
[paths]
watch_folder = "~/VoiceDrop"
output_folder = "~/VoiceDrop/Transcripts"
# Extra folders are transcribed in place — originals are never moved.
extra_watch_folders = ["~/Downloads"]
extra_watch_extensions = [".m4a", ".qta"]

[transcription]
model = "nova-3"
language = "en"
diarize = true
smart_format = true
paragraphs = true
utterances = true

[cleanup]
# Lightly clean transcripts with the headless `claude` CLI (latest Sonnet).
enabled = true
model = "sonnet"

[behavior]
notification_on_complete = true
max_retries = 3
"""


class Config:
    """Application configuration loaded from TOML."""

    def __init__(self):
        self._data = self._load()
        self._ensure_folders()

    def _load(self) -> dict:
        """Load config from file, creating defaults if missing."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        if not CONFIG_FILE.exists():
            CONFIG_FILE.write_text(DEFAULT_TOML)
            return _deep_copy(DEFAULTS)

        with open(CONFIG_FILE, "rb") as f:
            data = tomllib.load(f)

        # Merge with defaults so new keys are always present
        merged = _deep_copy(DEFAULTS)
        for section, values in data.items():
            if section in merged and isinstance(values, dict):
                merged[section].update(values)
            else:
                merged[section] = values
        return merged

    def _ensure_folders(self):
        """Create watch and output folders if they don't exist."""
        self.watch_folder.mkdir(parents=True, exist_ok=True)
        self.output_folder.mkdir(parents=True, exist_ok=True)

    @property
    def watch_folder(self) -> Path:
        return Path(self._data["paths"]["watch_folder"]).expanduser()

    @property
    def output_folder(self) -> Path:
        return Path(self._data["paths"]["output_folder"]).expanduser()

    @property
    def extra_watch_folders(self) -> list[Path]:
        return [Path(p).expanduser() for p in self._data["paths"].get("extra_watch_folders", [])]

    @property
    def extra_watch_extensions(self) -> frozenset[str]:
        exts = self._data["paths"].get("extra_watch_extensions", [])
        return frozenset(e.lower() for e in exts)

    @property
    def cleanup_enabled(self) -> bool:
        return self._data["cleanup"]["enabled"]

    @property
    def cleanup_model(self) -> str:
        return self._data["cleanup"]["model"]

    @property
    def transcription(self) -> dict:
        return self._data["transcription"]

    @property
    def max_retries(self) -> int:
        return self._data["behavior"]["max_retries"]

    @property
    def notification_on_complete(self) -> bool:
        return self._data["behavior"]["notification_on_complete"]


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts of primitives."""
    out = {}
    for k, v in d.items():
        out[k] = _deep_copy(v) if isinstance(v, dict) else v
    return out
