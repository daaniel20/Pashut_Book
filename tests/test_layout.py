"""Automatic checks for the album layout (task 2.2).

The layout part needs no Pillow. The drawing part (render.py, build_album.py)
is skipped without Pillow:   .venv/bin/python -m unittest discover tests
"""

import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "album"))

import designs  # noqa: E402
import layout   # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFilter
    import build_album
    import render
except ImportError:  # Pillow not installed: skip the drawing tests
    Image = None


def fake_photos(count, seed=1, small=(), skip=()):
    rng = random.Random(seed)
    photos = []
    for n in range(1, count + 1):
        width, height = rng.choice([(4000, 3000), (3000, 4000), (3000, 3000)])
        grade = "skip" if n in skip else "small" if n in small else "ok"
        photos.append(SimpleNamespace(name=f"{n:03d}", width=width, height=height, grade=grade))
    return photos


def placed(album):
    return [spot.photo for page in album.pages for spot in page.spots]


class LayoutTest(unittest.TestCase):
    def test_every_good_photo_is_used_once_in_order(self):
        photos = fake_photos(60, skip={5, 6})
        album = layout.make_album(photos, "classic")
        names = placed(album)
        expected = [p.name for p in photos if p.grade != "skip"]
        self.assertEqual(sorted(names), expected)
        self.assertEqual(album.left_out, ["005", "006"])
        # Photos may swap places on a page, but each page follows the one before.
        pages = [sorted(s.photo for s in page.spots) for page in album.pages if page.spots]
        for before, after in zip(pages, pages[1:]):
            self.assertLess(max(before), min(after))

    def test_page_count(self):
        for count in (30, 60, 100):
            album = layout.make_album(fake_photos(count), "colorful")
            self.assertGreaterEqual(len(album.pages), designs.MIN_PAGES)
            self.assertLessEqual(len(album.pages), designs.MAX_PAGES)
            self.assertEqual(len(album.pages) % designs.PAGE_MULTIPLE, 0)
            self.assertEqual(album.notes, [])

    def test_few_photos_warns_the_owner(self):
        album = layout.make_album(fake_photos(9), "classic")
        self.assertEqual(len(placed(album)), 9)
        self.assertEqual(len(album.pages) % designs.PAGE_MULTIPLE, 0)
        self.assertTrue(album.notes)

    def test_page_sizes_add_up_and_have_variety(self):
        for count in range(1, 101):
            sizes = layout.page_sizes(count)
            self.assertEqual(sum(sizes), count)
            self.assertTrue(all(1 <= s <= 4 for s in sizes))
        self.assertIn(1, layout.page_sizes(60))   # some single-photo pages

    def test_lower_quality_photos_only_in_small_spots(self):
        photos = fake_photos(60, small=set(range(1, 61, 3)))
        for design in designs.DESIGNS:
            album = layout.make_album(photos, design)
            grades = {p.name: p.grade for p in photos}
            for page in album.pages:
                for spot in page.spots:
                    if grades[spot.photo] == "small":
                        self.assertTrue(spot.small, f"{spot.photo} on {page.template}")

    def test_spots_stay_on_the_page(self):
        album = layout.make_album(fake_photos(80), "colorful")
        for page in [album.cover] + album.pages:
            for s in page.spots:
                self.assertGreaterEqual(s.x, 0)
                self.assertGreaterEqual(s.y, 0)
                self.assertLessEqual(s.x + s.width, album.width + 0.01)
                self.assertLessEqual(s.y + s.height, album.height + 0.01)

    def test_hebrew_pages_start_on_the_right(self):
        album = layout.make_album(fake_photos(60), "classic")
        page = next(p for p in album.pages if p.template in ("two_side", "four"))
        self.assertGreater(page.spots[0].x, page.spots[1].x)

    def test_colorful_has_no_edge_to_edge_photos(self):
        album = layout.make_album(fake_photos(60), "colorful")
        self.assertNotIn("full", [p.template for p in album.pages])

    def test_no_usable_photos(self):
        with self.assertRaises(ValueError):
            layout.make_album(fake_photos(3, skip={1, 2, 3}), "classic")


@unittest.skipIf(Image is None, "Pillow is not installed")
class DrawingTest(unittest.TestCase):
    def test_hebrew_title_order(self):
        self.assertEqual(render.visual_order("החופשה באילת 2026"), "2026 תליאב השפוחה")
        self.assertEqual(render.visual_order("סבתא (70)"), "(70) אתבס")
        self.assertEqual(render.visual_order("Family"), "Family")

    def test_build_a_whole_album(self):
        def photo(seed, size, blur=False):
            rng = random.Random(seed)
            image = Image.new("RGB", size, "white")
            draw = ImageDraw.Draw(image)
            for _ in range(200):
                x, y = rng.randrange(size[0]), rng.randrange(size[1])
                draw.rectangle((x, y, x + 80, y + 40),
                               fill=tuple(rng.randrange(256) for _ in range(3)))
            if blur:
                image = image.filter(ImageFilter.GaussianBlur(10))
            from io import BytesIO
            buffer = BytesIO()
            image.save(buffer, "JPEG")
            return buffer.getvalue()

        photos = [(f"{n:02d}.jpg", photo(n, (2400, 1800) if n % 2 else (1536, 2048)))
                  for n in range(1, 13)]
        photos.append(("13.jpg", photo(13, (2400, 1800), blur=True)))
        photos.append(("14.jpg", photos[0][1]))   # the same photo twice
        with tempfile.TemporaryDirectory() as folder:
            info = build_album.build(photos, "colorful", "החופשה באילת", Path(folder))
            self.assertEqual(info["used"], 12)
            self.assertEqual(info["left_out"], {"blurry": 1, "duplicate": 1, "unusable": 0})
            self.assertEqual(info["without_hd"], 6)
            files = {p.name for p in Path(folder).iterdir()}
            self.assertIn("album.html", files)
            self.assertIn("layout.json", files)
            self.assertIn("cover.jpg", files)
            self.assertIn(f"page-{info['pages']:02d}.jpg", files)
            with Image.open(Path(folder) / "page-01.jpg") as page:
                self.assertEqual(page.size, (designs.PAGE_WIDTH * 5, designs.PAGE_HEIGHT * 5))


if __name__ == "__main__":
    unittest.main()
