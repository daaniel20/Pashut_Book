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

    def test_page_plan_adds_up(self):
        for count in (1, 5, 9, 20, 38, 60, 100):
            photos = fake_photos(count)
            sizes = layout.plan_pages(photos, designs.DESIGNS["colorful"])
            self.assertEqual(sum(sizes), count)
            self.assertEqual(len(sizes), layout.page_count(count))
            self.assertTrue(all(1 <= s <= 4 for s in sizes))

    def test_page_count_follows_the_photos(self):
        self.assertEqual(layout.page_count(38), designs.MIN_PAGES)   # 15 → the minimum
        self.assertEqual(layout.page_count(60), 24)
        self.assertEqual(layout.page_count(100), 40)
        for count in range(designs.MIN_PAGES, 101):
            self.assertEqual(layout.page_count(count) % designs.PAGE_MULTIPLE, 0)

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

    def test_some_edge_to_edge_pages_but_not_in_a_row(self):
        for design in designs.DESIGNS:
            templates = [p.template for p in layout.make_album(fake_photos(60), design).pages]
            self.assertIn("full", templates)
            for a, b in zip(templates, templates[1:]):
                self.assertFalse(a == b == "full")

    def test_no_usable_photos(self):
        with self.assertRaises(ValueError):
            layout.make_album(fake_photos(3, skip={1, 2, 3}), "classic")


def photo(name, size, faces=(), grade="ok"):
    return SimpleNamespace(name=name, width=size[0], height=size[1], grade=grade,
                           faces=list(faces))


UPRIGHT, WIDE = (1536, 2048), (2048, 1536)


class FacesTest(unittest.TestCase):
    """Task 2.2 feedback: no cut faces, people or raised hands."""

    def shown(self, album, name):
        """(spot, crop) of a photo in the album."""
        return next((spot, spot.crop) for page in album.pages
                    for spot in page.spots if spot.photo == name)

    def assert_faces_kept(self, album, photos):
        for p in photos:
            spot, (cx, cy, cw, ch) = self.shown(album, p.name)
            for x, y, w, h in p.faces:
                self.assertGreaterEqual(x, cx - 1e-6, p.name)
                self.assertLessEqual(x + w, cx + cw + 1e-6, p.name)
                self.assertGreaterEqual(y, cy - 1e-6, p.name)
                self.assertLessEqual(y + h, cy + ch + 1e-6, p.name)

    def test_upright_photo_next_to_a_wide_one(self):
        # Page 4: an upright photo of a child was squeezed into a wide spot.
        photos = [photo("family", WIDE, [(0.3, 0.3, 0.1, 0.13), (0.5, 0.35, 0.08, 0.1)]),
                  photo("child", UPRIGHT, [(0.4, 0.12, 0.2, 0.15)])]
        name, order = layout._best_template(photos, [], False, designs.DESIGNS["colorful"])
        page = layout._page(name, order, "", designs.DESIGNS["colorful"])
        spot = next(s for s in page.spots if s.photo == "child")
        self.assertLess(spot.width / spot.height, 1)        # an upright spot
        self.assertGreater(spot.crop[3], 0.74)              # most of the photo shown

    def test_person_at_the_edge_is_not_cut(self):
        # Page 7 / 19: people from edge to edge of an upright photo.
        group = photo("group", UPRIGHT, [(0.02, 0.3, 0.12, 0.09), (0.45, 0.32, 0.1, 0.08),
                                         (0.85, 0.28, 0.12, 0.09)])
        # Cutting the sides would cut people: show the whole photo instead.
        self.assertIsNone(layout._cut(group, 0.58))
        # A photo with people loses at most a little (here 25% would be too much).
        self.assertIsNone(layout._cut(group, 1.0))
        self.assertEqual(layout._cut(group, 0.8)[2], 1)   # a slight trim top/bottom is fine
        album = layout.make_album([photo(f"{n:02d}", UPRIGHT) for n in range(20)] + [group],
                                  "colorful")
        self.assert_faces_kept(album, [group])

    def test_raised_hand_is_kept(self):
        # Page 23: a wide photo in a wider spot, a hand raised above the head.
        dad = photo("dad", WIDE, [(0.45, 0.35, 0.06, 0.08)])
        x, y, w, h = layout._cut(dad, 1.5)
        self.assertLessEqual(y, 0.35 - 0.08)                 # a head's height above the face is in
        self.assertLess(y, (1 - h) / 2)                      # cut more from the bottom

    def test_tall_photos_stay_big(self):
        # Page 11: two tall (phone-screen) photos were shown tiny.
        tall = (1152, 2048)
        for count in (2, 3):
            group = [photo(f"t{n}", tall, [(0.3, 0.2, 0.2, 0.1)]) for n in range(count)]
            style = designs.DESIGNS["colorful"]
            name, order = layout._best_template(group, [], False, style)
            page = layout._page(name, order, "", style)
            for spot in page.spots:
                self.assertGreater(spot.height, 0.45 * designs.PAGE_HEIGHT, name)

    def test_whole_albums_keep_every_face(self):
        rng = random.Random(3)
        photos = []
        for n in range(60):
            size = rng.choice([UPRIGHT, WIDE, (3000, 3000)])
            faces = [(rng.uniform(0, 0.85), rng.uniform(0, 0.8), 0.1, 0.12)
                     for _ in range(rng.randrange(0, 4))]
            photos.append(photo(f"{n:03d}", size, faces))
        for design in designs.DESIGNS:
            album = layout.make_album(photos, design)
            self.assert_faces_kept(album, photos)
            faces = {p.name: p.faces for p in photos}
            for page in album.pages:
                for spot in page.spots:
                    cut_off = 1 - spot.crop[2] * spot.crop[3]
                    limit = (layout.MAX_CUT_PEOPLE if faces[spot.photo] and page.template != "full"
                             else layout.MAX_CUT)
                    self.assertLessEqual(cut_off, limit + 1e-6)


class CoverTest(unittest.TestCase):
    """Task 2.2: the customer chooses the cover photo; it goes edge to edge."""

    def test_the_customers_cover_photo_edge_to_edge(self):
        photos = fake_photos(30)
        album = layout.make_album(photos, "colorful", "סבתא", cover="012")
        spot = album.cover.spots[0]
        self.assertEqual(spot.photo, "012")
        self.assertEqual((spot.x, spot.y, spot.width, spot.height),
                         (0, 0, designs.PAGE_WIDTH, designs.PAGE_HEIGHT))
        self.assertIn("012", placed(album))          # also inside the album

    def test_title_band_never_covers_a_face(self):
        low_faces = photo("low", (3000, 3000), [(0.4, 0.82, 0.1, 0.1)])
        album = layout.make_album([low_faces] + fake_photos(20), "classic", "x", cover="low")
        self.assertEqual(album.title_place, "top")
        high_faces = photo("high", (3000, 3000), [(0.4, 0.1, 0.1, 0.1)])
        album = layout.make_album([high_faces] + fake_photos(20), "classic", "x", cover="high")
        self.assertEqual(album.title_place, "bottom")

    def test_faces_everywhere_title_goes_below_a_smaller_photo(self):
        busy = photo("busy", (3000, 3000), [(0.4, 0.05, 0.1, 0.1), (0.4, 0.85, 0.1, 0.1)])
        album = layout.make_album([busy] + fake_photos(20), "classic", "x", cover="busy")
        self.assertEqual(album.title_place, "below")
        self.assertGreater(album.cover.spots[0].x, 0)

    def test_blurry_cover_choice_falls_back_and_tells_the_owner(self):
        photos = fake_photos(20, skip={3})
        album = layout.make_album(photos, "classic", None, cover="003")
        self.assertNotEqual(album.cover.spots[0].photo, "003")
        self.assertTrue(album.notes)


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
