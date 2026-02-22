# Whisper Drop

macOS menu bar app that watches a folder for Apple Voice Memo `.m4a` files and auto-transcribes them via Deepgram Nova 3.

Drop a file → get Markdown out. API key lives in macOS Keychain, never on disk.

## Install

```bash
git clone <this-repo> && cd voice-memo-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Usage

```bash
whisperdrop              # Launch the menu bar app
whisperdrop --install    # Start at login (LaunchAgent)
whisperdrop --uninstall  # Remove login item
```

On first launch, a dialog prompts for your Deepgram API key. Get one at [console.deepgram.com](https://console.deepgram.com).

### Default folders

| Folder | Purpose |
|--------|---------|
| `~/VoiceDrop/` | Drop `.m4a` files here |
| `~/Transcripts/` | Markdown output lands here |

Edit `~/.config/whisperdrop/config.toml` to change paths or transcription settings.

### How it works

1. Drop a `.m4a` into the watch folder (drag, AirDrop, whatever)
2. Whisper Drop detects it, waits for the write to finish
3. Sends it to Deepgram Nova 3 for transcription
4. Writes a clean Markdown file with speaker labels and timestamps
5. Moves the original to `~/VoiceDrop/.processed/`
6. Sends a macOS notification

### Optional: ffmpeg

If Deepgram rejects a file (rare edge case with iOS metadata), Whisper Drop will attempt to re-containerize it with `ffmpeg` if installed:

```bash
brew install ffmpeg
```

Not required — only used as a fallback.

## Second machine

Clone the repo, `pip install -e .`, run `whisperdrop`. Enter your API key when prompted. Each machine stores its own key in Keychain.
