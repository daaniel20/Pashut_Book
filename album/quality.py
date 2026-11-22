"""Photo quality check (task 2.1).

For each photo it finds:
- its size in pixels: big enough for a full page, only for small spots, or too small
- whether it's blurry
- whether it's a duplicate of another photo (the same photo twice, or an almost
  identical shot taken a second later). The best copy is kept.
- the date it was taken, if the photo still has it, to sort the album by date

Each photo gets a grade:
  "ok"     use it anywhere
  "small"  use it only in small spots (lower resolution, or a bit soft)
  "skip"   leave it out (blurry, too small, a duplicate, or can't be opened)

It only looks at photos and returns results. It doesn't know about WhatsApp
or Supabase, so the album builder can use it with photos from anywhere.

Needs Pillow (a common Python library for images): see requirements.txt.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO

from PIL import Image, ImageFilter, ImageOps, ImageStat

try:
    # iPhone photos (HEIC). Optional: without it, HEIC photos show as "can't open".
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

# ---------- the limits (tune them after the test album, task S.4) ----------
# Pixels on the long side of the photo. A full-page photo in a ~20x20 cm album
# needs about 2000 pixels to look sharp. WhatsApp without HD sends 2048
# (measured Nov 2026: 57 photos via the bot, all exactly 2048 on the long side);
# with HD a phone photo arrived at 5120.
FULL_PAGE_PIXELS = 2000
MIN_PIXELS = 800          # below this, too small even for a small spot
# Sharpness score (higher = sharper). Measured on the sharpest parts of the photo,
# so a portrait with a soft background is still fine.
BLURRY_BELOW = 80         # skip (owner test, Nov 2026: blurry shots scored 57-59)
SOFT_BELOW = 150          # small spots only (good photos scored 298+)
# How different two photos' fingerprints are (0 = identical, 64 = nothing alike).
# Measured: the same photo resized or recompressed = 0-1; shots taken a second
# apart = 2-9; different photos = 25 or more.
SAME_PHOTO_UNDER = 4      # the same photo sent twice
SIMILAR_UNDER = 11        # almost the same shot (e.g. 3 photos taken in a row)

ANALYSIS_SIZE = 1024      # photos are shrunk to this size for the checks (faster)


@dataclass
class PhotoCheck:
    name: str                     # file name, or the photo's number in the order
    width: int = 0
    height: int = 0
    sharpness: float = 0.0
    taken: datetime | None = None   # from the photo's own data, when it has it
    has_location: bool = False      # GPS still in the photo? (yes/no only; we never keep where)
    fingerprint: int = 0
    grade: str = "ok"
    problems: list = field(default_factory=list)  # short codes, see PROBLEM_TEXT
    duplicate_of: str | None = None

    @property
    def long_side(self):
        return max(self.width, self.height)


# What each problem means, in words for the owner.
PROBLEM_TEXT = {
    "unreadable": "can't open the file",
    "too_small": "too small to print",
    "small_size": "low resolution: small spots only",
    "blurry": "blurry",
    "soft": "a bit soft: small spots only",
    "duplicate": "the same photo was sent twice",
    "similar": "almost the same as another photo",
}


def check_photo(name, data):
    """Check one photo (its bytes). Returns a PhotoCheck."""
    result = PhotoCheck(name=name)
    try:
        image = Image.open(BytesIO(data))
        result.taken = _date_taken(image)
        result.has_location = _has_location(image)
        image = ImageOps.exif_transpose(image)  # turn it the right way up
        image.load()
    except Exception:
        result.problems.append("unreadable")
        result.grade = "skip"
        return result

    result.width, result.height = image.size
    gray = image.convert("L")
    gray.thumbnail((ANALYSIS_SIZE, ANALYSIS_SIZE))
    result.sharpness = round(_sharpness(gray), 1)
    result.fingerprint = _fingerprint(gray)

    if result.long_side < MIN_PIXELS:
        result.problems.append("too_small")
    elif result.long_side < FULL_PAGE_PIXELS:
        result.problems.append("small_size")
    if result.sharpness < BLURRY_BELOW:
        result.problems.append("blurry")
    elif result.sharpness < SOFT_BELOW:
        result.problems.append("soft")
    result.grade = _grade(result.problems)
    return result


def check_all(photos):
    """Check many photos. photos is a list of (name, bytes), in the order received.

    Returns the results sorted for the album: by date taken when the photos
    have dates, otherwise in the order received. Duplicates are marked "skip",
    keeping the best copy.
    """
    results = [check_photo(name, data) for name, data in photos]
    _mark_duplicates(results)
    return sort_by_date(results)


def sort_by_date(results):
    """Photos with a date, oldest first. Photos without a date stay next to the
    photo received just before them (customers usually send them in order)."""
    last_date = datetime.min
    keyed = []
    for position, result in enumerate(results):
        if result.taken:
            last_date = result.taken
        keyed.append((result.taken or last_date, position, result))
    return [result for _, _, result in sorted(keyed, key=lambda k: (k[0], k[1]))]


# ---------- how the checks work ----------

def _sharpness(gray):
    """Find edges in the photo, then measure how strong they are in the sharpest
    parts. A blurry photo has weak edges everywhere."""
    edges = gray.filter(ImageFilter.Kernel((3, 3), (0, 1, 0, 1, -4, 1, 0, 1, 0),
                                           scale=1, offset=128))
    # Pillow leaves the outer pixels unfiltered: cut them off.
    edges = edges.crop((2, 2, edges.width - 2, edges.height - 2))
    width, height = edges.size
    tiles = []
    for row in range(4):
        for col in range(4):
            box = (col * width // 4, row * height // 4,
                   (col + 1) * width // 4, (row + 1) * height // 4)
            tiles.append(ImageStat.Stat(edges.crop(box)).var[0])
    best = sorted(tiles, reverse=True)[:3]
    return sum(best) / len(best)


def _fingerprint(gray):
    """A 64-bit "fingerprint" of what the photo looks like (a difference hash).
    Two copies of the same photo have the same or nearly the same fingerprint,
    even if one is smaller or more compressed."""
    small = gray.resize((9, 8), Image.Resampling.LANCZOS)
    pixels = small.tobytes()  # one number (0-255) per pixel
    bits = 0
    for row in range(8):
        for col in range(8):
            left, right = pixels[row * 9 + col], pixels[row * 9 + col + 1]
            bits = (bits << 1) | (left > right)
    return bits


def _difference(a, b):
    return bin(a.fingerprint ^ b.fingerprint).count("1")


def _mark_duplicates(results):
    readable = [r for r in results if "unreadable" not in r.problems]
    # Best copies first: higher grade, then more pixels, then sharper.
    rank = {"ok": 0, "small": 1, "skip": 2}
    readable.sort(key=lambda r: (rank[r.grade], -r.width * r.height, -r.sharpness))
    kept = []
    for result in readable:
        original = min(kept, key=lambda k: _difference(k, result), default=None)
        if original and _difference(original, result) < SIMILAR_UNDER:
            result.duplicate_of = original.name
            result.problems.append("duplicate" if _difference(original, result)
                                   < SAME_PHOTO_UNDER else "similar")
            result.grade = "skip"
        else:
            kept.append(result)


def _grade(problems):
    if {"unreadable", "too_small", "blurry", "duplicate"} & set(problems):
        return "skip"
    if {"small_size", "soft"} & set(problems):
        return "small"
    return "ok"


def _date_taken(image):
    """The date the camera saved in the photo, if it's still there.
    (Photos sent in WhatsApp usually lose it; photos sent as a file keep it.)"""
    try:
        exif = image.getexif()
        value = exif.get_ifd(0x8769).get(36867) or exif.get(306)  # DateTimeOriginal, DateTime
        return datetime.strptime(str(value).strip("\x00 "), "%Y:%m:%d %H:%M:%S") if value else None
    except Exception:
        return None


def _has_location(image):
    """True if the photo still holds a GPS location. Only says yes or no: the
    place itself is never read out or saved (photos of children are private)."""
    try:
        gps = image.getexif().get_ifd(0x8825)  # the GPS part of the photo's data
        return 2 in gps and 4 in gps           # has a latitude and a longitude
    except Exception:
        return False
