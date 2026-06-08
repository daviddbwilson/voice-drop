"""Quick CLI transcription — processes all audio files in the watch folder once."""

from .config import Config
from .keychain import get_api_key
from .pipeline import process_file
from .watcher import SUPPORTED_EXTENSIONS, Job, WatchFolder, archive_file, existing_audio


def main():
    config = Config()
    api_key = get_api_key()
    if not api_key:
        print("No API key set. Run:")
        print('  python3 -c "from whisperdrop.keychain import set_api_key; set_api_key(\'YOUR_KEY\')"')
        return

    folder = WatchFolder(config.watch_folder, SUPPORTED_EXTENSIONS, archive=True)
    files = existing_audio(folder)
    if not files:
        print(f"No audio files in {config.watch_folder}")
        return

    for f in files:
        print(f"Transcribing: {f.name}...")
        out = process_file(Job(f, folder), config, api_key)
        archive_file(f, folder.path)
        print(f"  → {out.name}")

    print("Done.")


if __name__ == "__main__":
    main()
