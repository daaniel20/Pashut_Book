"""Automatic checks for the photo quality check (task 2.1).

Makes pretend photos (random shapes), so no real photos are needed.
Needs Pillow:   .venv/bin/python -m unittest discover tests
"""

import random
import sys
import unittest
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "album"))

try:
    from PIL import Image, ImageDraw, ImageFilter
    import quality
except ImportError:  # Pillow not installed: skip these tests
    Image = None


def make_photo(seed, size=(2400, 1800)):
    """A pretend photo: lots of random shapes, sharp edges."""
    rng = random.Random(seed)
    image = Image.new("RGB", size, tuple(rng.randrange(256) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(300):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        r = rng.randrange(10, 200)
        color = tuple(rng.randrange(256) for _ in range(3))
        if rng.random() < 0.5:
            draw.ellipse((x, y, x + r, y + r), fill=color)
        else:
            draw.rectangle((x, y, x + r, y + r // 2), fill=color)
    return image


def to_bytes(image, date=None):
    buffer = BytesIO()
    exif = Image.Exif()
    if date:
        exif.get_ifd(0x8769)[36867] = date
    image.save(buffer, "JPEG", quality=85, exif=exif)
    return buffer.getvalue()


@unittest.skipIf(Image is None, "Pillow is not installed")
class QualityTest(unittest.TestCase):
    def test_sharp_big_photo_is_ok(self):
        result = quality.check_photo("a", to_bytes(make_photo(1)))
        self.assertEqual(result.grade, "ok", result)

    def test_blurry_photo_is_left_out(self):
        blurry = make_photo(2).filter(ImageFilter.GaussianBlur(8))
        result = quality.check_photo("a", to_bytes(blurry))
        self.assertIn("blurry", result.problems)
        self.assertEqual(result.grade, "skip")

    def test_sizes(self):
        medium = quality.check_photo("a", to_bytes(make_photo(3, (1600, 1200))))
        self.assertEqual(medium.problems, ["small_size"])
        self.assertEqual(medium.grade, "small")
        tiny = quality.check_photo("b", to_bytes(make_photo(3, (640, 480))))
        self.assertIn("too_small", tiny.problems)
        self.assertEqual(tiny.grade, "skip")

    def test_not_a_photo(self):
        result = quality.check_photo("a", b"this is not a photo")
        self.assertEqual(result.problems, ["unreadable"])
        self.assertEqual(result.grade, "skip")

    def test_duplicates_keep_the_best_copy(self):
        photo = make_photo(4)
        small_copy = photo.resize((1200, 900))
        shifted = photo.crop((30, 0, 2400, 1800))   # like the next shot in a burst
        results = quality.check_all([
            ("small copy", to_bytes(small_copy)),
            ("original", to_bytes(photo)),
            ("shifted", to_bytes(shifted)),
            ("other", to_bytes(make_photo(5))),
        ])
        by_name = {r.name: r for r in results}
        self.assertEqual(by_name["original"].grade, "ok")
        self.assertEqual(by_name["small copy"].problems[-1], "duplicate")
        self.assertEqual(by_name["small copy"].duplicate_of, "original")
        self.assertIn(by_name["shifted"].problems[-1], ["duplicate", "similar"])
        self.assertEqual(by_name["other"].grade, "ok")

    def test_sorted_by_date_when_photos_have_one(self):
        results = quality.check_all([
            ("march", to_bytes(make_photo(6), "2026:03:01 10:00:00")),
            ("no date", to_bytes(make_photo(7))),
            ("january", to_bytes(make_photo(8), "2026:01:15 09:30:00")),
        ])
        self.assertEqual([r.name for r in results], ["january", "march", "no date"])
        self.assertEqual(results[0].taken.month, 1)


if __name__ == "__main__":
    unittest.main()
