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

import whatsapp  # noqa: E402

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


if __name__ == "__main__":
    unittest.main()
