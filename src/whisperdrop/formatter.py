"""Format Deepgram transcription JSON into clean Markdown.

Produces a Markdown file with YAML frontmatter (compatible with Obsidian/Logseq)
and speaker-labeled utterances with timestamps.
"""

import re
from datetime import datetime, timezone
from pathlib import Path


def format_transcription(deepgram_response: dict, source_filename: str) -> str:
    """Convert a Deepgram JSON response to a Markdown string.

    Args:
        deepgram_response: Full Deepgram API response dict
        source_filename: Original audio filename (used for title)

    Returns:
        Complete Markdown string with YAML frontmatter and body
    """
    results = deepgram_response.get("results", {})
    metadata = deepgram_response.get("metadata", {})
    utterances = results.get("utterances", [])
    channels = results.get("channels", [])

    # Title from filename (strip extension)
    title = Path(source_filename).stem

    # Duration from metadata
    duration_secs = metadata.get("duration", 0)
    duration_str = _format_duration(duration_secs)

    # Count unique speakers
    speakers = set()
    for utt in utterances:
        speakers.add(utt.get("speaker", 0))
    speaker_count = len(speakers) if speakers else 1
    multi_speaker = speaker_count > 1

    # Build frontmatter
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frontmatter = (
        f"---\n"
        f"title: \"{_escape_yaml(title)}\"\n"
        f"transcribed: {now}\n"
        f"duration: {duration_str}\n"
        f"source: \"{_escape_yaml(source_filename)}\"\n"
        f"model: {metadata.get('model_info', {}).get('name', 'nova-3') if metadata.get('model_info') else 'nova-3'}\n"
        f"speakers: {speaker_count}\n"
        f"---\n"
    )

    # Build body
    body_parts = [f"\n# {title}\n"]

    if utterances:
        # Use utterances for speaker-segmented output
        for utt in utterances:
            start = utt.get("start", 0)
            timestamp = _format_timestamp(start)
            text = utt.get("transcript", "").strip()
            if not text:
                continue

            if multi_speaker:
                speaker = utt.get("speaker", 0)
                body_parts.append(f"\n**Speaker {speaker}** ({timestamp})\n{text}\n")
            else:
                body_parts.append(f"\n({timestamp})\n{text}\n")
    elif channels:
        # Fallback: use channel paragraphs if no utterances
        for channel in channels:
            for alt in channel.get("alternatives", []):
                paragraphs = alt.get("paragraphs", {}).get("paragraphs", [])
                for para in paragraphs:
                    sentences = para.get("sentences", [])
                    text = " ".join(s.get("text", "") for s in sentences).strip()
                    if text:
                        body_parts.append(f"\n{text}\n")

    return frontmatter + "\n".join(body_parts)


def make_output_filename(source_filename: str) -> str:
    """Generate an output .md filename with timestamp suffix to prevent collisions.

    Example: "Weekly Standup.m4a" → "Weekly Standup_20260221-1430.md"
    """
    stem = Path(source_filename).stem
    # Sanitize: remove characters that are problematic in filenames
    stem = re.sub(r'[<>:"/\\|?*]', '_', stem)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    return f"{stem}_{timestamp}.md"


def _format_duration(seconds: float) -> str:
    """Format seconds into 'Xm Ys' string."""
    if seconds <= 0:
        return "0s"
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    if minutes > 0:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def _format_timestamp(seconds: float) -> str:
    """Format seconds into 'M:SS' timestamp."""
    minutes = int(seconds) // 60
    secs = int(seconds) % 60
    return f"{minutes}:{secs:02d}"


def _escape_yaml(s: str) -> str:
    """Escape quotes in a YAML string value."""
    return s.replace('"', '\\"')
