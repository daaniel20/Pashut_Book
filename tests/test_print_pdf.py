"""Automatic checks for the print PDF (task 2.3).

Needs Pillow (skipped without it):   .venv/bin/python -m unittest discover tests
"""

import json
import random
import re
import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "album"))

import layout   # noqa: E402

try:
    from PIL import Image, ImageDraw
    import build_album
    import print_pdf
    import printer
    import render
except ImportError:  # Pillow not installed
    Image = None


def photo_bytes(seed, size):
    rng = random.Random(seed)
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for _ in range(200):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        colour = tuple(rng.randrange(256) for _ in range(3))
        draw.rectangle((x, y, x + 60, y + 60), fill=colour, outline="black", width=3)
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


@unittest.skipIf(Image is None, "Pillow is not installed")
class BleedTest(unittest.TestCase):
    def test_full_page_photo_grows_into_the_bleed_without_changing_shape(self):
        spot = layout.Spot("a", 0, 0, 200, 200, False, crop=(0.125, 0, 0.75, 1))
        grown = render.with_bleed(spot, 200, 200, 3)
        self.assertEqual((grown.x, grown.y, grown.width, grown.height), (0, 0, 206, 206))
        cx, cy, cw, ch = grown.crop
        self.assertTrue(0 <= cx and 0 <= cy and cx + cw <= 1 + 1e-9 and cy + ch <= 1 + 1e-9)
        # Same shape as before: the photo is never stretched.
        self.assertAlmostEqual(cw / ch, 0.75 / 1)
        # The wide photo had more on the sides: it shows more there.
        self.assertLess(cx, 0.125)

    def test_photo_away_from_the_edge_only_moves(self):
        spot = layout.Spot("a", 10, 20, 80, 60, True, crop=(0, 0.1, 1, 0.8))
        grown = render.with_bleed(spot, 200, 200, 3)
        self.assertEqual((grown.x, grown.y, grown.width, grown.height), (13, 23, 80, 60))
        self.assertEqual(grown.crop, (0, 0.1, 1, 0.8))


@unittest.skipIf(Image is None, "Pillow is not installed")
class PrintPdfTest(unittest.TestCase):
    def test_print_files_from_a_built_album(self):
        sizes = [(1600, 1200), (1200, 1600), (1400, 1400)]
        photos = [(f"{n:03d}.jpg", photo_bytes(n, sizes[n % 3])) for n in range(1, 13)]
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            build_album.build(photos, "classic", "סבתא 70", folder)
            plan = json.loads((folder / "layout.json").read_text(encoding="utf-8"))
            album = layout.Album.from_dict(plan)
            self.assertEqual(json.loads(json.dumps(album.to_dict())), plan)   # read back exactly

            old_dpi = printer.DPI
            printer.DPI = 60   # small pages: a fast test
            try:
                report = print_pdf.make_print_files(album, photos, folder)
            finally:
                printer.DPI = old_dpi
            pages = (folder / "print-pages.pdf").read_bytes()
            cover = (folder / "print-cover.pdf").read_bytes()
            self.assertTrue(pages.startswith(b"%PDF-") and pages.rstrip().endswith(b"%%EOF"))
            self.assertEqual(len(re.findall(rb"/Type /Page ", pages)), len(album.pages))
            self.assertEqual(len(re.findall(rb"/Type /Page ", cover)), 1)
            # Page = trim size + bleed on each side; the TrimBox marks the cut.
            points = 72 / 25.4
            media = [float(v) for v in re.search(rb"/MediaBox \[([^\]]+)\]", pages)[1].split()]
            trim = [float(v) for v in re.search(rb"/TrimBox \[([^\]]+)\]", pages)[1].split()]
            self.assertAlmostEqual(media[2], (album.width + 2 * printer.BLEED) * points, 2)
            self.assertAlmostEqual(trim[0], printer.BLEED * points, 2)
            self.assertAlmostEqual(trim[2] - trim[0], album.width * points, 2)
            # These small test photos are far too small for print: reported.
            self.assertTrue(report["problems"])

            # Rebuilding the album removes the old print files.
            build_album.build(photos, "classic", "סבתא 70", folder)
            self.assertFalse((folder / "print-pages.pdf").exists())

    def test_resolution_check(self):
        album = layout.Album("classic", None, 200, 200, layout.Page("cover", "#FFFFFF", [
            layout.Spot("big", 0, 0, 200, 200, False)]))
        album.pages = [layout.Page("one", "#FFFFFF", [layout.Spot("small", 10, 10, 180, 180, False)])]
        data = {"big": photo_bytes(1, (2400, 2400)), "small": photo_bytes(2, (900, 900))}
        problems, warnings = print_pdf.check_resolution(album, data)
        self.assertEqual(len(problems), 1)          # 900 px on 18 cm = 127 DPI
        self.assertIn("page 1", problems[0])
        self.assertEqual(warnings, [])              # 2400 px on 20 cm = 305 DPI

    def test_missing_photo_is_an_error(self):
        album = layout.Album("classic", None, 200, 200, layout.Page("cover", "#FFFFFF", [
            layout.Spot("gone", 0, 0, 200, 200, False)]))
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                print_pdf.make_print_files(album, [], Path(folder))


if __name__ == "__main__":
    unittest.main()
