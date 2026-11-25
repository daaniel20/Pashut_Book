"""Shared helpers: read the private .env file and the customer-facing texts.

Customer texts live in server/texts/<language>.json, not inside the code,
so adding Russian, Arabic or English later means adding one file.
"""

import json
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
TEXTS_DIR = Path(__file__).resolve().parent / "texts"
PAGES_DIR = Path(__file__).resolve().parent / "pages"
MEDIA_DIR = Path(__file__).resolve().parent / "media"   # e.g. the HD how-to clip


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


# The album's price and shipping, in shekels (task 3.2). Not final: change them
# in .env (PRICE=150, SHIPPING=30) without touching the code. The ROI Google
# Sheet is the source for these numbers.
DEFAULT_PRICE = 150
DEFAULT_SHIPPING = 30


def prices(env=None):
    """(album price, shipping) in whole shekels, from .env or the defaults."""
    env = read_env() if env is None else env

    def number(name, default):
        try:
            return int(float(env.get(name, default)))
        except ValueError:
            return default
    return number("PRICE", DEFAULT_PRICE), number("SHIPPING", DEFAULT_SHIPPING)
