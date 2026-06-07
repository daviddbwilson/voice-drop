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
    from . import notify
    from .keychain import get_api_key
    from .ledger import Ledger
    from .pipeline import process_file
    from .transcriber import TranscriptionError
    from .watcher import Watcher, build_watch_folders, finalize_failure, finalize_success, prime_queue

    logger = logging.getLogger(__name__)

    api_key = get_api_key()
    if not api_key:
        logger.error("No API key set. Run: python3 -c \"from whisperdrop.keychain import set_api_key; set_api_key('YOUR_KEY')\"")
        sys.exit(1)

    queue: Queue = Queue()
    ledger = Ledger(CONFIG_DIR / "processed.json")
    folders = build_watch_folders(config)

    prime_queue(folders, queue, ledger)

    watcher = Watcher(folders, queue, ledger)
    watcher.start()

    # Graceful shutdown on Ctrl+C or SIGTERM
    running = True

    def stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    logger.info("Watching headlessly (Ctrl+C to stop)")

    while running:
        try:
            job = queue.get(timeout=1)
        except Empty:
            continue

        # Re-read key each time in case it was updated
        api_key = get_api_key()
        if not api_key:
            logger.error("API key missing, skipping %s", job.path.name)
            continue

        logger.info("Transcribing: %s", job.path.name)
        try:
            out = process_file(job, config, api_key)
        except TranscriptionError as e:
            logger.error("Transcription failed for %s: %s", job.path.name, e)
            finalize_failure(job)
            continue
        except Exception:
            logger.exception("Unexpected error processing %s", job.path.name)
            finalize_failure(job)
            continue

        finalize_success(job, ledger)
        logger.info("Done: %s", out.name)
        if config.notification_on_complete:
            notify.transcription_complete(out)

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
