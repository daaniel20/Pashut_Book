"""Automatic checks for checking the cover photo when it arrives (task 2.5).

The bot side uses a real Orders with a pretend Supabase and a pretend check
tool (no Pillow needed). The album side (album/check_cover.py) makes pretend
photos and is skipped without Pillow.
Run:   python3 -m unittest discover tests
"""

import random
import sys
import unittest
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "album"))
sys.path.insert(0, str(ROOT / "tests"))

import cover_check  # noqa: E402
import orders  # noqa: E402
from settings import load_texts  # noqa: E402
from test_orders import PHONE, FakeDatabase  # noqa: E402

try:
    from PIL import Image, ImageDraw, ImageFilter
    import check_cover
except ImportError:  # Pillow not installed: skip the album-side checks
    Image = None

TEXTS = load_texts("he")


class BotSideTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.sent = []
        self.ready = []
        self.orders = orders.Orders(self.db, on_ready=lambda *a: self.ready.append(a))
        self.result = {"ok": True, "problem": None, "dpi": 300, "without_hd": False}
        self.tool_calls = []
        checks = cover_check.CoverChecks(self.orders, lambda p, m: self.sent.append(m) or True,
                                         TEXTS, run_tool=self.fake_tool)
        self.orders.on_cover = checks.run      # run at once instead of in the background
        self.orders.wait_for_photos = lambda *a: True   # the photo is saved at once
        self.orders.answer(PHONE, "text", "שלום", TEXTS)
        self.orders.answer(PHONE, "button", "design_classic", TEXTS)

    def fake_tool(self, order_id, number):
        self.tool_calls.append(number)
        return self.result

    def test_good_cover(self):
        replies, job = self.orders.answer(PHONE, "photo", {"id": "m1"}, TEXTS)
        self.assertIn("בודקים", replies[0]["text"])
        self.assertEqual(self.tool_calls, [1])
        self.assertIn("יפה", self.sent[0]["text"])
        self.assertEqual(self.db.orders[0]["step"], "photos")

    def test_small_cover(self):
        self.result = {"ok": False, "problem": "small", "dpi": 146, "without_hd": True}
        self.orders.answer(PHONE, "photo", {"id": "m1"}, TEXTS)
        self.assertEqual([b["id"] for b in self.sent[0]["buttons"]], ["cover_new", "cover_keep"])
        self.assertEqual(self.db.orders[0]["step"], "cover_problem")

    def test_photo_not_saved_in_time_is_accepted(self):
        self.orders.wait_for_photos = lambda *a: False
        self.orders.answer(PHONE, "photo", {"id": "m1"}, TEXTS)
        self.assertEqual(self.tool_calls, [])          # not checked
        self.assertIn("יפה", self.sent[0]["text"])     # but the customer goes on

    def test_customer_started_over_meanwhile(self):
        self.orders.on_cover = lambda *a: None         # the check runs later
        self.orders.answer(PHONE, "photo", {"id": "m1"}, TEXTS)
        order_id = self.db.orders[0]["id"]
        self.orders.answer(PHONE, "text", "אלבום חדש", TEXTS)
        self.assertEqual(self.orders.cover_checked(PHONE, order_id, 1, self.result, TEXTS), [])


def make_photo(size, blur=False, seed=1):
    rng = random.Random(seed)
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    for _ in range(300):
        x, y = rng.randrange(size[0]), rng.randrange(size[1])
        r = rng.randrange(10, 200)
        draw.rectangle((x, y, x + r, y + r // 2), fill=tuple(rng.randrange(256) for _ in range(3)))
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(12))
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=90)
    return buffer.getvalue()


@unittest.skipIf(Image is None, "needs Pillow (.venv)")
class AlbumSideTest(unittest.TestCase):
    def test_hd_upright_photo_is_fine(self):
        result = check_cover.check("a", make_photo((3000, 4000)))
        self.assertEqual((result["ok"], result["problem"]), (True, None))
        self.assertGreaterEqual(result["dpi"], 300)

    def test_wide_photo_without_hd_is_too_small(self):
        # The owner's cover: a wide photo without HD printed at 146 DPI.
        result = check_cover.check("a", make_photo((2048, 1152)))
        self.assertEqual((result["ok"], result["problem"]), (False, "small"))
        self.assertTrue(result["without_hd"])
        self.assertLess(result["dpi"], 150)

    def test_upright_photo_without_hd_is_fine(self):
        result = check_cover.check("a", make_photo((1536, 2048)))
        self.assertTrue(result["ok"])

    def test_blurry_photo(self):
        result = check_cover.check("a", make_photo((3000, 4000), blur=True))
        self.assertEqual(result["problem"], "blurry")

    def test_unreadable_file_does_not_worry_the_customer(self):
        self.assertTrue(check_cover.check("a", b"not a photo")["ok"])


if __name__ == "__main__":
    unittest.main()
