"""Shared helpers: read the private .env file and the customer-facing texts.

Customer texts live in server/texts/<language>.json, not inside the code,
so adding Russian, Arabic or English later means adding one file.
"""

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
TEXTS_DIR = Path(__file__).resolve().parent / "texts"


def read_env(path=ENV_FILE):
    """Read simple NAME=value lines from the .env file."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def load_texts(language="he"):
    """Return all customer-facing texts for one language."""
    path = TEXTS_DIR / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))
