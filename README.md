# Whisper Drop

Watches a folder for Apple Voice Memo `.m4a` files and auto-transcribes them via Deepgram Nova 3. Drop a file, get Markdown out. Runs as a background service via LaunchAgent.

API key lives in macOS Keychain — never on disk.

## Setup (fresh machine)

```bash
# 1. Clone and install
git clone <this-repo> ~/code/voice-memo-agent
cd ~/code/voice-memo-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# 2. Store your Deepgram API key (goes straight into Keychain)
python3 -c "from whisperdrop.keychain import set_api_key; set_api_key('YOUR_DEEPGRAM_KEY')"

# 3. Start at login + start right now
whisperdrop --install
launchctl load ~/Library/LaunchAgents/com.whisperdrop.plist
```

That's it. Drop `.m4a` files into `~/VoiceDrop/` and transcripts appear automatically.

Get a Deepgram API key at [console.deepgram.com](https://console.deepgram.com) if you don't have one. Each machine stores its own key in Keychain — no syncing, no export.

## Folder layout

```
~/VoiceDrop/
├── *.m4a              ← drop files here
├── Transcripts/       ← markdown output
├── .processed/        ← archived originals
└── .failed/           ← failed files (retry via whisperdrop --once)
```

Edit `~/.config/whisperdrop/config.toml` to change paths or transcription settings.

## Commands

```bash
whisperdrop              # Watch folder and transcribe continuously
whisperdrop --once       # Process existing files and exit
whisperdrop --install    # Register as a login item (LaunchAgent)
whisperdrop --uninstall  # Remove the login item
```

## How it works

1. File watcher (`watchdog` + macOS FSEvents) detects new `.m4a` — zero CPU when idle
2. Waits for file size to stabilize (handles slow writes, AirDrop, etc.)
3. POSTs audio to Deepgram Nova 3 with diarization + smart formatting
4. Writes Markdown with YAML frontmatter (Obsidian/Logseq compatible) and speaker labels
5. Archives original to `.processed/`
6. On failure, quarantines to `.failed/` — run `whisperdrop --once` to retry

## Logs

```bash
cat ~/.config/whisperdrop/stderr.log    # recent activity
cat ~/.config/whisperdrop/whisperdrop.log  # full rotating log
```

## Manage the service

```bash
# Check if running
launchctl list | grep whisperdrop

# Restart
launchctl unload ~/Library/LaunchAgents/com.whisperdrop.plist
launchctl load ~/Library/LaunchAgents/com.whisperdrop.plist

# Stop permanently
whisperdrop --uninstall
```

## Optional: ffmpeg

If Deepgram rejects a file (rare edge case with iOS metadata), Whisper Drop will re-containerize it with `ffmpeg` if installed:

```bash
brew install ffmpeg
```

Not required — only used as a fallback.
