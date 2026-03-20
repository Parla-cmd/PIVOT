"""
Config loader
-------------
Reads .env from the project root and sets values as environment variables.
Provides get(key, default) for all modules to use.
No external dependencies -- parses .env manually.
"""
import os
import re
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_ENV_FILE = _ROOT / ".env"

_loaded: dict[str, str] = {}


def load():
    """Load .env into os.environ. Called once at startup."""
    global _loaded
    if not _ENV_FILE.exists():
        return

    with open(_ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # KEY=value  or  KEY="value"  or  KEY='value'
            m = re.match(r'^([A-Z_][A-Z0-9_]*)=(.*)$', line)
            if not m:
                continue
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            _loaded[key] = val
            os.environ.setdefault(key, val)  # don't override existing env vars


def get(key: str, default: str = "") -> str:
    """Return config value — checks env first, then .env, then default."""
    return os.environ.get(key, _loaded.get(key, default))
