"""Deepgram API key storage via macOS Keychain.

Uses the `keyring` library which wraps the native Keychain on macOS.
The key is never written to disk, config files, or logs.
"""

import keyring

SERVICE = "com.whisperdrop.api"
USERNAME = "deepgram"


def get_api_key() -> str | None:
    """Retrieve the Deepgram API key from Keychain. Returns None if not set."""
    key = keyring.get_password(SERVICE, USERNAME)
    return key if key else None


def set_api_key(key: str) -> None:
    """Store the Deepgram API key in Keychain."""
    keyring.set_password(SERVICE, USERNAME, key.strip())


def has_api_key() -> bool:
    """Check whether a Deepgram API key exists in Keychain."""
    return get_api_key() is not None
