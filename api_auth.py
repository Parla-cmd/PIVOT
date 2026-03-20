"""
API Key Authentication for PIVOT Remote Control API.

Keys are stored in .env.api (one per line: PIVOT_API_KEY=<key>).
Generate a new key with: python -c "from api_auth import generate_key; print(generate_key())"
"""

import os
import secrets
import hashlib
from pathlib import Path

_ENV_API_FILE = Path(".env.api")
_ENV_VAR = "PIVOT_API_KEY"


def _load_keys() -> set[str]:
    """Load all valid API keys from environment and .env.api file."""
    keys: set[str] = set()

    # Keys from environment
    for key_str in (os.environ.get(_ENV_VAR, "") or "").split(","):
        key_str = key_str.strip()
        if key_str:
            keys.add(key_str)

    # Keys from .env.api file
    if _ENV_API_FILE.exists():
        for line in _ENV_API_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith("PIVOT_API_KEY="):
                key_str = line[len("PIVOT_API_KEY="):].strip()
                if key_str:
                    keys.add(key_str)

    return keys


def validate_key(api_key: str) -> bool:
    """Return True if the given key is valid."""
    if not api_key:
        return False
    valid_keys = _load_keys()
    return any(
        secrets.compare_digest(api_key, k)
        for k in valid_keys
    )


def generate_key() -> str:
    """Generate a new random API key (64 hex chars)."""
    return secrets.token_hex(32)


def save_key(key: str, file: Path = _ENV_API_FILE) -> None:
    """Append a key to the .env.api file."""
    with file.open("a") as f:
        f.write(f"PIVOT_API_KEY={key}\n")
