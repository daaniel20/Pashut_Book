"""Automatic checks for the customer's preview images (task 2.4).

The image tests need Pillow (skipped without it):
  .venv/bin/python -m unittest discover tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "album"))

import preview_links  # noqa: E402
import whatsapp  # noqa: E402
from settings import load_texts  # noqa: E402

try:
    from PIL import Image
    import preview
except ImportError:  # Pillow not installed
    Image = None


@unittest.skipIf(Image is None, "Pillow is not installed")
class PreviewTest(unittest.TestCase):
    def test_pages_are_grouped_like_an_open_hebrew_book(self):
        self.assertEqual(preview.spreads(6), [[None], [1], [2, 3], [4, 5], [6]])

    def test_previews_are_small_and_marked(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            colours = ["red", "blue", "green", "yellow", "purple"]
            Image.new("RGB", (1000, 1000), "black").save(folder / "cover.jpg")
            for n, colour in enumerate(colours, start=1):
                Image.new("RGB", (1000, 1000), colour).save(folder / f"page-{n:02d}.jpg")
            Image.new("RGB", (1000, 1000), "orange").save(folder / "page-06.jpg")

            made = preview.make_previews(folder, 6)

            self.assertEqual([m["pages"] for m in made], [[], [1], [2, 3], [4, 5], [6]])
            names = [Path(m["file"]).name for m in made]
            self.assertEqual(names, ["00-cover.jpg", "01-page-1.jpg", "02-pages-2-3.jpg",
                                     "03-pages-4-5.jpg", "04-page-6.jpg"])
            spread = Image.open(made[2]["file"]).convert("RGB")
            # Two pages side by side, each too small to print.
            self.assertLessEqual(spread.height, preview.PAGE_PIXELS + preview.NUMBER_STRIP)
            self.assertEqual(spread.width, 2 * preview.PAGE_PIXELS + preview.GAP)
            # Right to left: page 2 (blue) on the right, page 3 (green) on the left.
            right = spread.getpixel((spread.width - 5, 5))
            left = spread.getpixel((5, 5))
            self.assertGreater(right[2], 150)
            self.assertGreater(left[1], 80)
            self.assertLess(left[0], 80)
            # The mark changes the page: not every pixel is the plain colour.
            page = spread.crop((0, 0, preview.PAGE_PIXELS, preview.PAGE_PIXELS))
            self.assertGreater(len(page.getcolors(1_000_000)), 2)

            # Building again replaces the old previews.
            preview.make_previews(folder, 2)
            self.assertEqual(len(list((folder / preview.FOLDER).glob("*.jpg"))), 3)


class LinkTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.links = root / "links"
        self.album = root / "album"
        (self.album / "preview").mkdir(parents=True)
        for name in ("00-cover.jpg", "01-page-1.jpg"):
            (self.album / "preview" / name).write_bytes(b"jpg")
        (self.album / "layout.json").write_text("{}")
        self.previews = [{"file": str(self.album / "preview" / "00-cover.jpg"), "pages": []},
                         {"file": str(self.album / "preview" / "01-page-1.jpg"), "pages": [1]}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_link_opens_only_its_own_preview_images(self):
        code = preview_links.create(self.album, self.previews, 2, links_dir=self.links)
        self.assertEqual(len(code), 32)
        data = preview_links.find(code, links_dir=self.links)
        page = preview_links.page_html(code, data, load_texts("he"))
        self.assertIn(f"/album/{code}/01-page-1.jpg", page)
        self.assertIn("עמוד 1", page)
        self.assertIn("noindex", page)
        self.assertIsNotNone(preview_links.image_path(data, "00-cover.jpg"))
        for name in ("layout.json", "../layout.json", "../../.env", ""):
            self.assertIsNone(preview_links.image_path(data, name), name)

    def test_wrong_or_old_codes_open_nothing(self):
        for code in ("", "short", "../" * 11 + "xx", "a" * 32):
            self.assertIsNone(preview_links.find(code, links_dir=self.links))
        old = preview_links.create(self.album, self.previews, 2, links_dir=self.links, days=-1)
        self.assertIsNone(preview_links.find(old, links_dir=self.links))

    def test_a_new_build_replaces_the_old_link(self):
        first = preview_links.create(self.album, self.previews, 2, links_dir=self.links)
        second = preview_links.create(self.album, self.previews, 2, links_dir=self.links)
        self.assertIsNone(preview_links.find(first, links_dir=self.links))
        self.assertIsNotNone(preview_links.find(second, links_dir=self.links))


class UploadTest(unittest.TestCase):
    def test_image_is_uploaded_then_sent(self):
        calls = []

        class FakeWhatsApp(whatsapp.WhatsApp):
            def _call(self, url, data=None, timeout=20, content_type="application/json"):
                calls.append((url, data, content_type))
                return json.dumps({"id": "media-7"}).encode()

        wa = FakeWhatsApp({"WHATSAPP_PHONE_NUMBER_ID": "123", "WHATSAPP_ACCESS_TOKEN": "t"})
        with tempfile.NamedTemporaryFile(suffix=".jpg") as file:
            file.write(b"JPEGDATA")
            file.flush()
            wa.send("972500000000", {"image_file": file.name, "caption": "עמוד 1"})

        upload, message = calls
        self.assertTrue(upload[0].endswith("/123/media"))
        self.assertIn("multipart/form-data; boundary=", upload[2])
        self.assertIn(b"JPEGDATA", upload[1])
        self.assertIn(b'name="messaging_product"\r\n\r\nwhatsapp', upload[1])
        sent = json.loads(message[1])
        self.assertEqual(sent["type"], "image")
        self.assertEqual(sent["image"], {"id": "media-7", "caption": "עמוד 1"})

    def test_link_button_with_the_cover_on_top(self):
        calls = []

        class FakeWhatsApp(whatsapp.WhatsApp):
            def _call(self, url, data=None, timeout=20, content_type="application/json"):
                calls.append(data)
                return json.dumps({"id": "media-8"}).encode()

        wa = FakeWhatsApp({"WHATSAPP_PHONE_NUMBER_ID": "123", "WHATSAPP_ACCESS_TOKEN": "t"})
        with tempfile.NamedTemporaryFile(suffix=".jpg") as file:
            file.write(b"JPEG")
            file.flush()
            wa.send("972500000000", {"text": "מוכן", "image_file": file.name,
                                     "link": {"button": "לצפייה", "url": "https://x/album/C"}})
        sent = json.loads(calls[-1])["interactive"]
        self.assertEqual(sent["type"], "cta_url")
        self.assertEqual(sent["header"], {"type": "image", "image": {"id": "media-8"}})
        self.assertEqual(sent["action"]["parameters"],
                         {"display_text": "לצפייה", "url": "https://x/album/C"})


if __name__ == "__main__":
    unittest.main()
