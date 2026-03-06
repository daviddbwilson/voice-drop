"""Quick CLI transcription — processes all audio files in the watch folder."""

from pathlib import Path

from .config import Config
from .formatter import format_transcription, make_output_filename
from .keychain import get_api_key
from .transcriber import SUPPORTED_FORMATS, transcribe
from .watcher import archive_file


def main():
    config = Config()
    api_key = get_api_key()
    if not api_key:
        print("No API key set. Run:")
        print('  python3 -c "from whisperdrop.keychain import set_api_key; set_api_key(\'YOUR_KEY\')"')
        return

    # Collect all supported audio files
    files = []
    for ext in SUPPORTED_FORMATS.keys():
        files.extend(config.watch_folder.glob(f"*{ext}"))
    files = sorted(set(files))  # dedupe and sort
    
    if not files:
        print(f"No audio files in {config.watch_folder}")
        return

    for f in files:
        print(f"Transcribing: {f.name}...")
        result = transcribe(f, api_key, config.transcription, config.max_retries)
        md = format_transcription(result, f.name)
        out = config.output_folder / make_output_filename(f.name)
        out.write_text(md, encoding="utf-8")
        archive_file(f, config.watch_folder)
        print(f"  → {out.name}")

    print("Done.")


if __name__ == "__main__":
    main()
