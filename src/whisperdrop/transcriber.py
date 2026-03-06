"""Deepgram Nova 3 transcription via REST API.

Sends audio as binary POST to /v1/listen.
Retries on network errors and 429s. Optional ffmpeg fallback if Deepgram
rejects the file (400) and ffmpeg is available.
"""

import logging
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"

# Supported audio formats: extension -> MIME type
SUPPORTED_FORMATS = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".opus": "audio/opus",
    ".webm": "audio/webm",
    ".flac": "audio/flac",
}


def get_content_type(file_path: Path) -> str:
    """Get the MIME type for an audio file based on extension."""
    ext = file_path.suffix.lower()
    return SUPPORTED_FORMATS.get(ext, "audio/mpeg")  # default fallback


class TranscriptionError(Exception):
    """Raised when transcription fails after all retries."""
    pass


class AuthError(TranscriptionError):
    """Raised when the API key is invalid (401)."""
    pass


def transcribe(file_path: Path, api_key: str, config: dict, max_retries: int = 3) -> dict:
    """Transcribe an audio file via Deepgram.

    Args:
        file_path: Path to the audio file (m4a, ogg, mp3, wav, etc.)
        api_key: Deepgram API key
        config: Transcription settings dict (model, diarize, etc.)
        max_retries: Maximum retry attempts for transient errors

    Returns:
        Deepgram JSON response as a dict

    Raises:
        AuthError: If the API key is invalid
        TranscriptionError: If transcription fails after all retries
    """
    params = {
        "model": config.get("model", "nova-3"),
        "smart_format": str(config.get("smart_format", True)).lower(),
        "diarize": str(config.get("diarize", True)).lower(),
        "paragraphs": str(config.get("paragraphs", True)).lower(),
        "utterances": str(config.get("utterances", True)).lower(),
        "language": config.get("language", "en"),
    }

    audio_data = file_path.read_bytes()
    content_type = get_content_type(file_path)

    # Try the raw file first
    result = _post_with_retry(audio_data, api_key, params, max_retries, content_type)
    if result is not None:
        return result

    # If we got here, we got a 400. Try ffmpeg re-containerization as fallback.
    if not shutil.which("ffmpeg"):
        raise TranscriptionError(
            f"Deepgram rejected {file_path.name} and ffmpeg is not installed. "
            "Install ffmpeg (brew install ffmpeg) to enable automatic re-containerization."
        )

    logger.info("Attempting ffmpeg re-containerization for %s", file_path.name)
    recontainerized = _ffmpeg_recontainerize(file_path)
    if recontainerized is None:
        raise TranscriptionError(
            f"ffmpeg failed to re-containerize {file_path.name}"
        )

    try:
        audio_data = recontainerized.read_bytes()
        result = _post_with_retry(audio_data, api_key, params, max_retries=1, content_type=content_type)
        if result is not None:
            return result
        raise TranscriptionError(
            f"Deepgram still rejected {file_path.name} after ffmpeg re-containerization"
        )
    finally:
        recontainerized.unlink(missing_ok=True)


def _post_with_retry(audio_data: bytes, api_key: str, params: dict, max_retries: int, content_type: str = "audio/mpeg") -> dict | None:
    """POST audio to Deepgram with retry logic.

    Returns the response dict on success, None if the file was rejected (400).
    Raises AuthError on 401, TranscriptionError on exhausted retries.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=300) as client:
                response = client.post(
                    DEEPGRAM_URL,
                    params=params,
                    headers={
                        "Authorization": f"Token {api_key}",
                        "Content-Type": content_type,
                    },
                    content=audio_data,
                )

            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                raise AuthError(
                    "Invalid Deepgram API key. Update it via the menu bar → Change API Key."
                )

            if response.status_code == 400:
                # File rejected — caller may try ffmpeg fallback
                logger.warning("Deepgram rejected the file (400): %s", response.text[:200])
                return None

            if response.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Rate limited (429), waiting %ds before retry", wait)
                time.sleep(wait)
                continue

            # Other error codes
            last_error = f"Deepgram returned {response.status_code}: {response.text[:200]}"
            logger.warning(last_error)

        except (httpx.NetworkError, httpx.TimeoutException) as e:
            last_error = str(e)
            wait = 2 ** attempt
            logger.warning("Network error (attempt %d/%d): %s, retrying in %ds",
                           attempt + 1, max_retries, e, wait)
            time.sleep(wait)

    raise TranscriptionError(f"Transcription failed after {max_retries} attempts: {last_error}")


def _ffmpeg_recontainerize(file_path: Path) -> Path | None:
    """Re-containerize an M4A file with ffmpeg to fix metadata issues.

    Creates a temp file — caller is responsible for cleanup.
    """
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".m4a", delete=False)
        tmp.close()
        result = subprocess.run(
            ["ffmpeg", "-i", str(file_path), "-c", "copy", "-y", tmp.name],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            logger.info("ffmpeg re-containerization succeeded")
            return Path(tmp.name)
        else:
            logger.warning("ffmpeg failed: %s", result.stderr[:200])
            Path(tmp.name).unlink(missing_ok=True)
            return None
    except Exception:
        logger.exception("ffmpeg re-containerization error")
        return None
