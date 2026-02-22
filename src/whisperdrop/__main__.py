"""CLI entry point for Whisper Drop.

Usage:
    whisperdrop              Launch the menu bar app
    whisperdrop --install    Register as a login item (LaunchAgent)
    whisperdrop --uninstall  Remove the login item
"""

import argparse
import logging
import plistlib
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import CONFIG_DIR, Config


def setup_logging():
    """Configure rotating file logger + stderr."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = CONFIG_DIR / "whisperdrop.log"

    handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=2, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(message)s",
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stderr_handler)


# --- LaunchAgent management ---

PLIST_LABEL = "com.whisperdrop"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_LABEL}.plist"


def _get_python_path() -> str:
    """Get the path to the current Python interpreter (should be in .venv)."""
    return sys.executable


def install_launch_agent():
    """Create a LaunchAgent plist so Whisper Drop starts at login."""
    python_path = _get_python_path()

    plist = {
        "Label": PLIST_LABEL,
        "ProgramArguments": [python_path, "-m", "whisperdrop"],
        "RunAtLoad": True,
        "LimitLoadToSessionType": "Aqua",
        "ProcessType": "Interactive",
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        },
        "StandardOutPath": str(CONFIG_DIR / "stdout.log"),
        "StandardErrorPath": str(CONFIG_DIR / "stderr.log"),
    }

    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Installed LaunchAgent: {PLIST_PATH}")
    print(f"  Python: {python_path}")
    print("  Whisper Drop will start automatically at login.")
    print("  To start it now: launchctl load", PLIST_PATH)


def uninstall_launch_agent():
    """Remove the LaunchAgent plist and unload it."""
    import subprocess

    if PLIST_PATH.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)],
                        capture_output=True)
        PLIST_PATH.unlink()
        print(f"Removed LaunchAgent: {PLIST_PATH}")
    else:
        print("No LaunchAgent found — nothing to remove.")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        prog="whisperdrop",
        description="macOS menu bar voice memo transcription agent",
    )
    parser.add_argument("--install", action="store_true",
                        help="Register as a login item (LaunchAgent)")
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove the login item")
    args = parser.parse_args()

    if args.install:
        install_launch_agent()
        return

    if args.uninstall:
        uninstall_launch_agent()
        return

    # Normal launch: start the menu bar app
    setup_logging()
    config = Config()

    from .app import WhisperDropApp
    app = WhisperDropApp(config)
    app.run()


if __name__ == "__main__":
    main()
