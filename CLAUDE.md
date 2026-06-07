# Whisper Drop

macOS menu bar app that watches a folder for `.m4a` voice memos and auto-transcribes them via Deepgram Nova 3.

## Architecture

- **`src/whisperdrop/`** — all source code
- **`config.py`** — TOML config at `~/.config/whisperdrop/config.toml`, path expansion, folder creation
- **`keychain.py`** — API key in macOS Keychain via `keyring` (service: `com.whisperdrop.api`)
- **`watcher.py`** — `watchdog` FSEvents watcher over one or more folders (`WatchFolder`), `Job` queue items, stable-size debounce; plus source-lifecycle helpers (`prime_queue`, `finalize_success`, `finalize_failure`)
- **`ledger.py`** — persistent JSON record of transcribed files for "in place" folders (dedup without moving)
- **`transcriber.py`** — POST binary to Deepgram REST API, retry with backoff, optional ffmpeg fallback
- **`formatter.py`** — Deepgram JSON → Markdown with YAML frontmatter and speaker labels
- **`cleanup.py`** — light-touch transcript cleanup via the headless `claude` CLI (best-effort, falls back to raw)
- **`pipeline.py`** — shared per-file pipeline: transcribe → format → (clean) → write; used by both entry points
- **`notify.py`** — macOS "transcript ready" notification (`terminal-notifier` reveal-on-click, `osascript` fallback)
- **`app.py`** — `rumps.App` menu bar UI, threading, notifications
- **`__main__.py`** — CLI entry point, wires everything together, handles `--install`/`--uninstall`

## Key Design Decisions

- **Two kinds of watched folder**: the primary `~/VoiceDrop` *archives* originals to `.processed/`; `extra_watch_folders` (e.g. `~/Downloads`) are watched *in place* — originals never move.
- **Dedup**: archive folders dedup via the move-to-archive (no state); in-place folders dedup via the persistent `ledger.py`. The startup backlog in in-place folders is seeded as already-seen, so only newly-arriving files get transcribed.
- **Cleaned is canonical**: when cleanup runs, the cleaned transcript is `<name>.md` and the verbatim one is kept as `<name>.raw.md`. The completion notification fires only after the cleaned file exists and points at it.
- **Cleanup is light + best-effort**: latest Sonnet via headless `claude`; mainly resolves `Speaker N` → real names on explicit self-identification. Any failure leaves the raw transcript untouched.
- **Stable-size debounce**: Check file size twice 1s apart instead of fixed timer — handles large files and slow transfers
- **ffmpeg truly optional**: Only attempted if Deepgram rejects the raw file AND ffmpeg is installed
- **API key never touches disk**: Keychain only, never logged, never in config

## Dev Setup

```bash
cd ~/code/voice-memo-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
whisperdrop  # launches menu bar app
```

## Testing

Stdlib-only unit tests (no Deepgram/macOS deps needed) cover `ledger`, `cleanup`, and `notify`:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

End-to-end is still manual: drop a `.m4a` into `~/VoiceDrop/` (or `~/Downloads/`) and check the Transcripts folder for output.
