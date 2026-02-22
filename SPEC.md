# Whisper Drop — Voice Memo Transcription Agent

> macOS menu bar app that watches a folder for Apple Voice Memo files and auto-transcribes them via Deepgram Nova 3.

## Overview

**Form factor:** Native macOS menu bar app (Python + rumps)
**Name:** Whisper Drop (working title)
**Repo:** `~/code/voice-memo-agent`

Drop a `.m4a` voice memo into the watch folder → it gets transcribed → a clean Markdown file appears in the output folder. The menu bar icon shows status at a glance.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Watch Folder │────▶│  File Watcher │────▶│  Transcriber │────▶│ Output Folder │
│  (~/Drop)     │     │  (watchdog)   │     │  (Deepgram)  │     │ (~/Transcripts)│
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                            │
                     ┌──────┴──────┐
                     │  Menu Bar   │
                     │  (rumps)    │
                     │  Status UI  │
                     └─────────────┘
```

### Components

1. **File Watcher** — `watchdog` library using macOS FSEvents. Monitors a configurable folder for new `.m4a` files. Debounces to avoid processing partial writes.
2. **Preprocessor** — Optional `ffmpeg` re-containerization if Deepgram rejects the raw Apple M4A (known edge case with iOS metadata). Falls back gracefully.
3. **Transcriber** — Sends audio to Deepgram REST API (`POST /v1/listen`). Uses Nova 3 with smart formatting, diarization, paragraphs, and utterances.
4. **Formatter** — Converts Deepgram JSON response into clean Markdown with speaker labels, timestamps, and metadata header.
5. **Menu Bar UI** — `rumps` status bar icon. Shows idle/processing/error states. Dropdown menu with recent transcriptions, settings, and quit.
6. **Config** — TOML settings file for paths, preferences. API key stored in macOS Keychain (never on disk).

## Security Model

This app handles a paid API key and processes potentially sensitive audio. Security is non-negotiable.

| Concern | Approach |
|---------|----------|
| **API key storage** | macOS Keychain via `keyring` library. Never written to disk, `.env`, or config files. |
| **First-run setup** | Native dialog prompts for API key, stores directly to Keychain. |
| **Key rotation** | Settings menu allows updating the key (overwrites in Keychain). |
| **Multi-machine install** | User re-enters key on each machine. No sync, no export. |
| **File permissions** | Watch/output folders validated on startup. No world-readable files. |
| **Network** | HTTPS only (Deepgram API). No other network calls. |
| **No telemetry** | Zero analytics, tracking, or phoning home. |
| **Dependencies** | Minimal, pinned, auditable. No unnecessary packages. |

## Configuration

Settings stored in `~/.config/whisperdrop/config.toml`:

```toml
[paths]
watch_folder = "~/VoiceDrop"          # Where to drop .m4a files
output_folder = "~/Transcripts"        # Where .md files land
archive_processed = true               # Move processed .m4a to subfolder

[transcription]
model = "nova-3"
language = "en"
diarize = true                         # Speaker labels
smart_format = true                    # Format dates, numbers, etc.
paragraphs = true                      # Group into paragraphs
utterances = true                      # Segment by speaker turns

[behavior]
launch_at_login = false                # Register as login item
notification_on_complete = true        # macOS notification when done
retry_on_failure = true                # Retry failed transcriptions
max_retries = 3
```

The API key is NOT in this file — it lives in Keychain only.

## File Processing Pipeline

```
1. New .m4a detected in watch folder
2. Wait 2 seconds (debounce — ensure write is complete)
3. Validate file (non-zero size, valid M4A header)
4. Extract metadata (title, duration, recording date from M4A tags)
5. Attempt Deepgram transcription
   └─ If rejected, re-containerize with ffmpeg and retry
6. Parse JSON response
7. Format as Markdown (see output format below)
8. Write .md to output folder
9. Optionally move .m4a to archive subfolder
10. Send macOS notification
11. Update menu bar status
```

## Output Format

Each transcription produces a Markdown file like:

```markdown
---
title: Weekly Standup Notes
recorded: 2026-02-21T10:30:00Z
transcribed: 2026-02-21T10:32:15Z
duration: 4m 23s
source: Weekly Standup Notes.m4a
model: nova-3
speakers: 2
---

# Weekly Standup Notes

**Speaker 0** (0:00)
Good morning everyone. Let's go around and share updates.

**Speaker 1** (0:05)
Sure. I wrapped up the API migration yesterday. The new endpoints are live
and passing all tests.

**Speaker 0** (0:15)
Great. Any blockers?

...
```

The YAML frontmatter makes these files compatible with Obsidian, Logseq, and other PKM tools.

## Menu Bar UI

**Icon states:**
- `●` Idle (ready) — subtle dot or microphone icon
- `↻` Processing — animated or different icon
- `✗` Error — red indicator

**Dropdown menu:**
```
Whisper Drop
──────────────
● Watching: ~/VoiceDrop
  Last: "Weekly Standup" (2 min ago)
──────────────
Recent Transcriptions ▸
  Weekly Standup Notes.md
  Client Call Feb 20.md
  Ideas for Q2 roadmap.md
──────────────
Open Watch Folder
Open Output Folder
──────────────
Settings...
  API Key: ●●●●●●● (Change)
  Watch Folder: ~/VoiceDrop
  Output Folder: ~/Transcripts
──────────────
Quit Whisper Drop
```

## Dependencies

| Package | Purpose | Size |
|---------|---------|------|
| `rumps` | Menu bar UI | Tiny |
| `watchdog` | File system monitoring (FSEvents) | Small |
| `keyring` | macOS Keychain access | Small |
| `httpx` | HTTP client for Deepgram API | Small |
| `tomli` / `tomllib` | TOML config parsing (stdlib in 3.11+) | Stdlib |

**Optional:**
| `ffmpeg` (system) | M4A re-containerization fallback | System install |

Total dependency footprint is minimal. No heavy frameworks.

## Distribution & Installation

**For personal use (both machines):**

1. Clone the repo
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -e .`
4. `whisperdrop` to launch (first run prompts for API key)
5. Optional: `whisperdrop --install-service` to register as login item

**Future (if desired):** Bundle with `py2app` into a standalone `.app` for drag-and-drop install. Skip code signing for personal use (right-click → Open to bypass Gatekeeper once).

## Tech Decisions & Rationale

| Decision | Why |
|----------|-----|
| **Python over Swift** | Faster to build, easier to maintain, David can read and modify it. Port to Swift later if desired. |
| **rumps over Electron/Tauri** | Lightweight (~50 lines for menu bar), native feel, no Chromium bloat. |
| **Keychain over .env** | Only secure option. An `.env` file with a Deepgram key on disk is a liability. |
| **TOML over JSON/YAML** | Human-readable, stdlib support in Python 3.11+, no footguns. |
| **httpx over requests** | Modern, async-capable, better timeout handling. |
| **Deepgram REST over SDK** | The SDK adds dependency weight. The REST API is one POST call. |
| **watchdog over polling** | Uses native FSEvents — instant detection, no CPU waste. |

## Non-Goals (v1)

- No GUI settings window (edit TOML + Keychain CLI for now)
- No audio format conversion beyond the M4A edge-case fix
- No batch processing of existing files (watches for new files only)
- No cloud sync or multi-device state
- No Electron, no web UI
- No auto-update mechanism
