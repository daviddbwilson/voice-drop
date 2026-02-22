# Whisper Drop

macOS menu bar app that watches a folder for `.m4a` voice memos and auto-transcribes them via Deepgram Nova 3.

## Architecture

- **`src/whisperdrop/`** — all source code
- **`config.py`** — TOML config at `~/.config/whisperdrop/config.toml`, path expansion, folder creation
- **`keychain.py`** — API key in macOS Keychain via `keyring` (service: `com.whisperdrop.api`)
- **`watcher.py`** — `watchdog` FSEvents watcher, handles `on_created` + `on_moved`, stable-size debounce
- **`transcriber.py`** — POST binary to Deepgram REST API, retry with backoff, optional ffmpeg fallback
- **`formatter.py`** — Deepgram JSON → Markdown with YAML frontmatter and speaker labels
- **`app.py`** — `rumps.App` menu bar UI, threading, notifications
- **`__main__.py`** — CLI entry point, wires everything together, handles `--install`/`--uninstall`

## Key Design Decisions

- **Dedup via move-to-archive**: Processed `.m4a` files move to `watch_folder/.processed/` — no in-memory state needed
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

Manual testing only for now. Drop a `.m4a` into `~/VoiceDrop/` and check `~/Transcripts/` for output.
