"""CLI entry point for Whisper Drop.

Usage:
    whisperdrop              Watch folder and transcribe (headless)
    whisperdrop --once       Process existing files and exit
    whisperdrop --install    Register as a login item (LaunchAgent)
    whisperdrop --uninstall  Remove the login item
"""

import argparse
import logging
import plistlib
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from queue import Empty, Queue

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
        "ProgramArguments": [python_path, "-m", "whisperdrop", "--watch"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},  # restart if it crashes
        "ProcessType": "Background",
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


# --- Headless watch mode ---

def run_watch(config: Config):
    """Run the watcher + transcriber headlessly (no GUI)."""
    from .formatter import format_transcription, make_output_filename
    from .keychain import get_api_key
    from .transcriber import AuthError, TranscriptionError, transcribe
    from .watcher import Watcher, archive_file, quarantine_file

    logger = logging.getLogger(__name__)

    api_key = get_api_key()
    if not api_key:
        logger.error("No API key set. Run: python3 -c \"from whisperdrop.keychain import set_api_key; set_api_key('YOUR_KEY')\"")
        sys.exit(1)

    queue: Queue = Queue()

    # Process any .m4a files already in the folder on startup
    for existing in sorted(config.watch_folder.glob("*.m4a")):
        if not existing.name.startswith("."):
            logger.info("Found existing file: %s", existing.name)
            queue.put(existing)

    watcher = Watcher(config.watch_folder, queue)
    watcher.start()

    # Graceful shutdown on Ctrl+C or SIGTERM
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    logger.info("Watching %s (headless mode, Ctrl+C to stop)", config.watch_folder)

    while running:
        try:
            file_path = queue.get(timeout=1)
        except Empty:
            continue

        # Re-read key each time in case it was updated
        api_key = get_api_key()
        if not api_key:
            logger.error("API key missing, skipping %s", file_path.name)
            continue

        logger.info("Transcribing: %s", file_path.name)
        try:
            result = transcribe(file_path, api_key, config.transcription, config.max_retries)
            md = format_transcription(result, file_path.name)
            out = config.output_folder / make_output_filename(file_path.name)
            out.write_text(md, encoding="utf-8")
            archive_file(file_path, config.watch_folder)
            logger.info("Done: %s", out.name)
        except AuthError as e:
            logger.error("Auth error: %s", e)
            quarantine_file(file_path, config.watch_folder)
        except TranscriptionError as e:
            logger.error("Transcription failed: %s", e)
            quarantine_file(file_path, config.watch_folder)
        except Exception as e:
            logger.exception("Unexpected error processing %s: %s", file_path.name, e)
            quarantine_file(file_path, config.watch_folder)

    watcher.stop()
    logger.info("Stopped.")


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        prog="whisperdrop",
        description="Voice memo transcription agent — watches a folder, transcribes .m4a files via Deepgram",
    )
    parser.add_argument("--watch", action="store_true",
                        help="Watch folder and transcribe continuously (default)")
    parser.add_argument("--once", action="store_true",
                        help="Process existing files and exit")
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

    setup_logging()
    config = Config()

    if args.once:
        from .cli import main as cli_main
        cli_main()
        return

    # Default: watch mode
    run_watch(config)


if __name__ == "__main__":
    main()
