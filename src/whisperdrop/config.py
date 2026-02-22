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
    },
    "transcription": {
        "model": "nova-3",
        "language": "en",
        "diarize": True,
        "smart_format": True,
        "paragraphs": True,
        "utterances": True,
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

[transcription]
model = "nova-3"
language = "en"
diarize = true
smart_format = true
paragraphs = true
utterances = true

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
