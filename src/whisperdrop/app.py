"""Menu bar application using rumps.

Shows a status icon in the macOS menu bar with controls for the
watch folder, output folder, and API key management. Runs the file
watcher and transcription pipeline in background threads.
"""

import logging
import subprocess
import threading
from queue import Empty, Queue

import AppKit
import rumps

from . import keychain, notify
from .config import CONFIG_DIR, Config
from .ledger import Ledger
from .pipeline import process_file
from .transcriber import AuthError, TranscriptionError
from .watcher import (
    Watcher,
    build_watch_folders,
    count_failed,
    finalize_failure,
    finalize_success,
    prime_queue,
    retry_failed,
)

logger = logging.getLogger(__name__)

# Menu bar title states
ICON_IDLE = "WD"
ICON_PROCESSING = "WD..."
ICON_ERROR = "WD!"


class WhisperDropApp(rumps.App):
    """macOS menu bar app for voice memo transcription."""

    def __init__(self, config: Config):
        super().__init__(ICON_IDLE, quit_button=None)
        self.config = config
        self.queue: Queue = Queue()
        self.ledger = Ledger(CONFIG_DIR / "processed.json")
        self.watcher: Watcher | None = None
        self._active_count = 0  # Number of files currently being processed
        self._active_lock = threading.Lock()

        # Build menu
        self.status_item = rumps.MenuItem(f"Watching: {self.config.watch_folder}")
        self.status_item.set_callback(None)

        self.retry_item = rumps.MenuItem("Retry Failed", callback=self._retry_failed)
        self.retry_item.set_callback(None)  # Hidden until there are failures

        self.menu = [
            self.status_item,
            None,  # separator
            rumps.MenuItem("Open Watch Folder", callback=self._open_watch_folder),
            rumps.MenuItem("Open Output Folder", callback=self._open_output_folder),
            self.retry_item,
            None,
            rumps.MenuItem("Change API Key...", callback=self._change_api_key),
            None,
            rumps.MenuItem("Quit Whisper Drop", callback=self._quit),
        ]

        # Timer to process queue items from the main thread context
        self._timer = rumps.Timer(self._poll_queue, 1)

    def _setup(self):
        """Called when the app starts. Starts watcher and checks for API key."""
        # Prompt for API key on first run
        if not keychain.has_api_key():
            self._prompt_api_key()

        # Start the file watcher across all configured folders
        folders = build_watch_folders(self.config)
        prime_queue(folders, self.queue, self.ledger)
        self.watcher = Watcher(folders, self.queue, self.ledger)
        self.watcher.start()
        self._timer.start()
        logger.info("Whisper Drop started")

    def _poll_queue(self, _timer):
        """Check for queued files and process them."""
        if not keychain.has_api_key():
            # Don't consume items — they stay in the queue until a key is set
            return

        try:
            job = self.queue.get_nowait()
        except Empty:
            return

        # Process in a background thread to keep UI responsive
        threading.Thread(target=self._process_file, args=(job,), daemon=True).start()

    def _process_file(self, job):
        """Transcribe a single queued file and write the output."""
        api_key = keychain.get_api_key()
        if not api_key:
            # Shouldn't happen (checked in _poll_queue), but re-queue defensively
            self.queue.put(job)
            return

        with self._active_lock:
            self._active_count += 1
            self.title = ICON_PROCESSING
        logger.info("Transcribing: %s", job.path.name)

        try:
            output_path = process_file(job, self.config, api_key)
        except AuthError as e:
            logger.error("Auth error: %s", e)
            finalize_failure(job)
            rumps.notification(
                "Whisper Drop", "Invalid API Key",
                "Your Deepgram API key is invalid. Update it via the menu bar.",
            )
            self._update_retry_menu()
        except TranscriptionError as e:
            logger.error("Transcription error: %s", e)
            finalize_failure(job)
            rumps.notification(
                "Whisper Drop", "Transcription Failed",
                f"{job.path.stem}: {str(e)[:150]}. Use Retry Failed to try again.",
            )
            self._update_retry_menu()
        except Exception as e:
            logger.exception("Unexpected error processing %s", job.path.name)
            finalize_failure(job)
            rumps.notification(
                "Whisper Drop", "Error",
                f"Failed to process {job.path.name}: {e}",
            )
            self._update_retry_menu()
        else:
            # Only archive/record and notify when transcription truly succeeded,
            # so a finalize error can't be mistaken for a transcription failure.
            finalize_success(job, self.ledger)
            if self.config.notification_on_complete:
                notify.transcription_complete(output_path)
        finally:
            with self._active_lock:
                self._active_count -= 1
                if self._active_count == 0:
                    self.title = ICON_IDLE

    def _prompt_api_key(self):
        """Show a dialog to enter the Deepgram API key."""
        response = rumps.Window(
            title="Whisper Drop — API Key",
            message="Enter your Deepgram API key.\nGet one at console.deepgram.com",
            default_text="",
            ok="Save",
            cancel="Cancel",
            dimensions=(320, 24),
        ).run()

        if response.clicked and response.text.strip():
            keychain.set_api_key(response.text)
            logger.info("API key saved to Keychain")

    def _change_api_key(self, _sender):
        """Menu action: update the API key."""
        self._prompt_api_key()

    def _retry_failed(self, _sender):
        """Menu action: move failed files back to watch folder for reprocessing."""
        n = retry_failed(self.config.watch_folder)
        if n > 0:
            logger.info("Retrying %d failed file(s)", n)
            rumps.notification(
                "Whisper Drop", "Retrying",
                f"Moved {n} file(s) back to watch folder.",
            )
        self._update_retry_menu()

    def _update_retry_menu(self):
        """Show/hide the Retry Failed menu item based on .failed/ contents."""
        n = count_failed(self.config.watch_folder)
        if n > 0:
            self.retry_item.title = f"Retry Failed ({n})"
            self.retry_item.set_callback(self._retry_failed)
        else:
            self.retry_item.title = "Retry Failed"
            self.retry_item.set_callback(None)

    def _open_watch_folder(self, _sender):
        """Menu action: open the watch folder in Finder."""
        subprocess.run(["open", str(self.config.watch_folder)])

    def _open_output_folder(self, _sender):
        """Menu action: open the output folder in Finder."""
        subprocess.run(["open", str(self.config.output_folder)])

    def _quit(self, _sender):
        """Menu action: quit the app."""
        if self.watcher:
            self.watcher.stop()
        rumps.quit_application()

    def run(self, **kwargs):
        """Override run to set up watcher after app starts."""
        # Create the NSApplication singleton and tell macOS this is a
        # menu-bar-only app (no Dock icon). Must happen before rumps.App.run()
        # creates its own run loop. Homebrew Python lacks LSUIElement in its
        # Info.plist, so without this the status item won't appear.
        app = AppKit.NSApplication.sharedApplication()
        app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
        self._setup()
        super().run(**kwargs)
