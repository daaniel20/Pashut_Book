"""Automatic checks for saving orders and photos (task 1.3).

Uses a pretend Supabase and a pretend WhatsApp, so it needs no internet.
Run:   python3 -m unittest discover tests
"""

import sys
import time
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import orders  # noqa: E402
from database import DatabaseError  # noqa: E402
from settings import load_texts  # noqa: E402
from whatsapp import WhatsAppError  # noqa: E402

TEXTS = load_texts("he")
PHONE = "972500000000"
orders.DELETE_DELAY_SECONDS = 0


# Most checks here are about other steps and send only a few photos, so the
# "only N photos, add more?" question (FewPhotosTest) is turned down for them.
GOOD_COVER = {"ok": True, "problem": None, "dpi": 300, "without_hd": False}
SMALL_COVER = {"ok": False, "problem": "small", "dpi": 146, "without_hd": True}


def setUpModule():
    global _real_few, _real_quiet
    _real_few = orders.conversation.FEW_PHOTOS
    orders.conversation.FEW_PHOTOS = 2
    # These checks tap "done" right after the photos; waiting for the photos to
    # stop arriving is checked in WaitForPhotosTest, with a short real wait.
    _real_quiet = orders.QUIET_SECONDS
    orders.QUIET_SECONDS = 0


def tearDownModule():
    orders.conversation.FEW_PHOTOS = _real_few
    orders.QUIET_SECONDS = _real_quiet


class FakeDatabase:
    def __init__(self):
        self.orders = []   # oldest first
        self.photos = []
        self.files = {}
        self.down = False

    def _check(self):
        if self.down:
            raise DatabaseError("pretend Supabase is down")

    def latest_order(self, phone):
        self._check()
        mine = [o for o in self.orders if o["phone"] == phone]
        return dict(mine[-1]) if mine else None

    def create_order(self, phone, fields):
        self._check()
        row = dict(fields, phone=phone, id=str(uuid.uuid4()))
        self.orders.append(row)
        return dict(row)

    def update_order(self, order_id, fields):
        self._check()
        next(o for o in self.orders if o["id"] == order_id).update(fields)

    def add_photo(self, fields):
        self._check()
        if any(p["wa_media_id"] == fields["wa_media_id"] for p in self.photos):
            return None
        row = dict(fields, id=str(uuid.uuid4()))
        self.photos.append(row)
        return row

    def update_photo_size(self, photo_id, size):
        next(p for p in self.photos if p["id"] == photo_id)["size_bytes"] = size

    def remove_photo_row(self, photo_id):
        self.photos = [p for p in self.photos if p["id"] != photo_id]

    def upload(self, path, data, mime_type):
        self._check()
        self.files[path] = data

    def delete_order_photos(self, order_id):
        paths = [p["storage_path"] for p in self.photos if p["order_id"] == order_id]
        for path in paths:
            self.files.pop(path, None)
        self.photos = [p for p in self.photos if p["order_id"] != order_id]
        return len(paths)


class FakeWhatsApp:
    def __init__(self, fail_times=0):
        self.fail_times = fail_times

    def photo_info(self, media_id):
        if self.fail_times:
            self.fail_times -= 1
            raise WhatsAppError("pretend network hiccup")
        return {"url": "https://example/" + media_id, "file_size": 1000}

    def download(self, url):
        return b"photo bytes " + url.encode()


def photo(n):
    return {"id": f"media{n}", "mime_type": "image/jpeg"}


class OrdersTest(unittest.TestCase):
    def setUp(self):
        self.db = FakeDatabase()
        self.covers = []
        self.orders = orders.Orders(self.db, on_cover=lambda *a: self.covers.append(a))

    def say(self, kind, value=None):
        return self.orders.answer(PHONE, kind, value, TEXTS)

    def check_covers(self, result=GOOD_COVER):
        """Like cover_check.py: the cover photo is saved, then checked (task 2.5)."""
        replies = []
        while self.covers:
            phone, order_id, number = self.covers.pop(0)
            replies += self.orders.cover_checked(phone, order_id, number, result, TEXTS)
        return replies

    def send_photos(self, count, start=1):
        for n in range(start, start + count):
            replies, job = self.say("photo", photo(n))
            if job:
                order_id, number = job
                orders.save_photo(self.db, FakeWhatsApp(), order_id, number, photo(n))
                self.check_covers()

    def test_60_photos_are_all_saved(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(60)
        replies, _ = self.say("button", "photos_done")
        self.assertIn("קיבלנו 60 תמונות 👍", replies[0]["text"])
        order = self.db.orders[0]
        self.assertEqual(order["photo_count"], 60)
        self.assertEqual(order["step"], "cover")
        self.assertEqual(len(self.db.photos), 60)
        self.assertEqual(len(self.db.files), 60)
        self.assertIn(f"{order['id']}/001.jpg", self.db.files)
        self.assertIn(f"{order['id']}/060.jpg", self.db.files)

    def test_limit_photos_over_the_maximum_are_not_saved(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(orders.conversation.MAX_PHOTOS + 5)
        self.assertEqual(len(self.db.files), orders.conversation.MAX_PHOTOS)

    def test_bot_restart_remembers_the_customer(self):
        self.say("text", "שלום")
        self.say("button", "design_colorful")
        self.send_photos(3)
        restarted = orders.Orders(self.db)  # like turning the Mac off and on
        replies, _ = restarted.answer(PHONE, "button", "photos_done", TEXTS)
        self.assertIn("3", replies[0]["text"])
        self.assertEqual(len(self.db.orders), 1)

    def test_new_album_cancels_the_old_one_and_deletes_its_photos(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(5)
        self.say("text", "אלבום חדש")
        self.say("button", "restart_yes")   # "are you sure?" -> yes
        old, new = self.db.orders
        self.assertEqual(old["status"], "cancelled")
        self.assertEqual(new["status"], "collecting")
        # The deletion runs on a timer; wait for it.
        for _ in range(100):
            if not self.db.files:
                break
            time.sleep(0.01)
        self.assertEqual(self.db.files, {})

    def test_finished_album_is_kept_when_restarting_while_changing_it(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(3)
        self.say("button", "photos_done")
        self.say("button", "cover_no")
        self.say("button", "edit_title")       # changing the finished album…
        self.say("text", "אלבום חדש")          # …then starting a new one
        self.say("button", "restart_yes")
        self.assertNotEqual(self.db.orders[0]["status"], "cancelled")
        self.assertEqual(len(self.db.orders), 2)

    def test_finished_album_is_kept_when_starting_a_new_one(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(2)
        self.say("button", "photos_done")
        self.say("button", "cover_no")
        self.assertEqual(self.db.orders[0]["status"], "ready")
        self.say("text", "אלבום חדש")
        self.say("button", "restart_yes")   # "are you sure?" -> yes
        self.assertEqual(self.db.orders[0]["status"], "ready")
        self.assertEqual(len(self.db.files), 2)

    def test_same_photo_twice_is_saved_once(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        _, (order_id, number) = self.say("photo", photo(1))
        self.assertTrue(orders.save_photo(self.db, FakeWhatsApp(), order_id, number, photo(1)))
        self.assertTrue(orders.save_photo(self.db, FakeWhatsApp(), order_id, 2, photo(1)))
        self.assertEqual(len(self.db.files), 1)

    def test_network_hiccup_is_retried(self):
        self.say("text", "שלום")
        _, (order_id, number) = self.say("photo", photo(1))
        self.assertTrue(orders.save_photo(self.db, FakeWhatsApp(fail_times=2),
                                          order_id, number, photo(1), wait=0))
        self.assertEqual(len(self.db.files), 1)
        self.assertFalse(orders.save_photo(self.db, FakeWhatsApp(fail_times=5),
                                           order_id, 2, photo(2), wait=0))
        self.assertEqual(len(self.db.photos), 1)  # the failed one isn't listed

    def test_supabase_down_on_first_message(self):
        self.db.down = True
        with self.assertRaises(DatabaseError):
            self.say("text", "שלום")
        self.db.down = False
        replies, _ = self.say("text", "שלום")
        self.assertEqual(len(replies), 2)  # welcome + design buttons


class WaitForPhotosTest(unittest.TestCase):
    """"Done" tapped while HD photos are still arriving; photos after the summary."""

    def setUp(self):
        orders.QUIET_SECONDS = 0.3
        self.db = FakeDatabase()
        self.ready, self.sent, self.covers = [], [], []
        self.orders = orders.Orders(self.db, on_ready=lambda *a: self.ready.append(a),
                                    on_cover=lambda *a: self.covers.append(a))
        self.orders.send = lambda phone, message: self.sent.append(message)

    def tearDown(self):
        orders.QUIET_SECONDS = 0

    def say(self, kind, value=None):
        replies, job = self.orders.answer(PHONE, kind, value, TEXTS)
        if job:   # like bot.py: save the photo, then the cover check (task 2.5)
            orders.save_photo(self.db, FakeWhatsApp(), job[0], job[1], value)
            self.orders.photo_done(job[0], job[1])
            replies += self.check_covers(GOOD_COVER)
        return replies

    check_covers = OrdersTest.check_covers

    def wait_until(self, condition):
        for _ in range(100):
            if condition():
                return True
            time.sleep(0.02)
        return False

    def test_done_waits_until_the_photos_stop(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        for n in range(1, 4):
            self.say("photo", photo(n))
        replies = self.say("button", "photos_done")       # photos still arriving
        self.assertIn("מוודאים", replies[0]["text"])
        self.assertEqual(self.say("button", "photos_done"), [])   # a second tap: quiet
        for n in range(4, 6):
            self.say("photo", photo(n))                   # the last photos arrive
        self.assertTrue(self.wait_until(lambda: self.sent))
        self.assertIn("קיבלנו 5 תמונות", self.sent[0]["text"])   # the full count
        self.assertEqual(self.db.orders[0]["step"], "cover")
        self.assertNotIn("done_waiting", self.db.orders[0]["notes"])

    def test_done_after_a_pause_goes_on_at_once(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        for n in range(1, 4):
            self.say("photo", photo(n))
        time.sleep(0.35)
        replies = self.say("button", "photos_done")
        self.assertIn("קיבלנו 3 תמונות", replies[0]["text"])

    def test_count_is_sent_once_photos_stop(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        for n in range(1, 6):
            self.say("photo", photo(n))                  # the cover, then 4 more
        self.assertTrue(self.wait_until(lambda: self.sent))
        self.assertIn("קיבלנו 5 תמונות", self.sent[-1]["text"])
        self.assertIn("photos_done", [b["id"] for b in self.sent[-1]["buttons"]])
        self.assertIn("counted:5", self.db.orders[0]["notes"])

    def test_photo_after_the_summary_rebuilds_the_album(self):
        orders.QUIET_SECONDS = 0
        self.say("text", "שלום")
        self.say("button", "design_classic")
        for n in range(1, 4):
            self.say("photo", photo(n))
        self.say("button", "photos_done")
        self.say("button", "cover_no")
        self.assertEqual(len(self.ready), 1)
        replies = self.say("photo", photo(4))
        self.assertIn("נוסיף אותן", replies[0]["text"])
        self.assertEqual(self.say("photo", photo(5)), [])   # said once
        self.assertEqual(len(self.ready), 3)                # built again (album_job merges)
        self.assertEqual(self.db.orders[0]["photo_count"], 5)
        self.assertEqual(len(self.db.files), 5)


class AlbumReadyTest(unittest.TestCase):
    """Task 2.2: a complete order starts the album; resending in HD replaces the photos."""

    def setUp(self):
        self.db = FakeDatabase()
        self.ready = []
        self.covers = []
        self.orders = orders.Orders(self.db, on_ready=lambda *a: self.ready.append(a),
                                    on_cover=lambda *a: self.covers.append(a))

    def say(self, kind, value=None, cover=None):
        replies, job = self.orders.answer(PHONE, kind, value, TEXTS)
        if job:   # like bot.py: save the photo, then say it's done
            orders.save_photo(self.db, FakeWhatsApp(), job[0], job[1], value)
            self.orders.photo_done(job[0], job[1])
            replies += self.check_covers(cover or GOOD_COVER)
        return replies

    check_covers = OrdersTest.check_covers

    def finish(self, first=1, count=3):
        for n in range(first, first + count):
            self.say("photo", photo(n))
        self.say("button", "photos_done")

    def test_complete_order_starts_the_album_once(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.finish()
        self.say("button", "cover_no")
        order_id = self.db.orders[0]["id"]
        self.assertEqual(self.ready, [(PHONE, order_id)])
        self.say("text", "עוד משהו")
        self.assertEqual(len(self.ready), 1)

    def test_no_change_does_not_build_again(self):
        # Task 1.2b: "↩️ בלי שינוי" after the previews keeps the album as it is.
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.finish()
        self.say("button", "cover_no")
        order_id = self.db.orders[0]["id"]
        self.orders.add_note(PHONE, order_id, "previews_sent")
        self.say("button", "edit_menu")
        self.say("button", "edit_design")
        self.say("button", "no_change")
        self.assertEqual(len(self.ready), 1)
        self.assertTrue(self.orders.is_done(PHONE, order_id))
        self.say("button", "edit_design")
        self.say("button", "design_colorful")                # a real change: built again
        self.assertEqual(len(self.ready), 2)

    def test_resend_in_hd(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.finish()
        self.say("button", "cover_no")
        order_id = self.db.orders[0]["id"]
        self.assertTrue(self.orders.ask_hd(PHONE, order_id))
        self.assertEqual(self.db.orders[0]["step"], "hd_question")
        self.assertIn("hd_asked", self.orders.notes_of(PHONE, order_id))
        self.say("button", "hd_help")
        self.assertEqual(len(self.db.photos), 3)      # only the how-to: nothing deleted yet
        self.finish(first=10, count=2)                # the first new photo replaces the old ones
        self.assertEqual(len(self.db.photos), 2)
        self.assertIn(f"{order_id}/001.jpg", self.db.files)
        self.assertEqual(self.db.orders[0]["step"], "done")
        self.assertEqual(len(self.ready), 2)          # the album starts again

    def test_ask_hd_does_nothing_after_a_new_album(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.finish()
        self.say("button", "cover_no")
        old_order = self.db.orders[0]["id"]
        self.say("text", "אלבום חדש")
        self.say("button", "restart_yes")   # "are you sure?" -> yes
        self.assertFalse(self.orders.ask_hd(PHONE, old_order))
        self.assertIsNone(self.orders.notes_of(PHONE, old_order))

    def test_new_cover_photo_is_waited_for(self):
        # The owner's round 3 test: the album was rebuilt before the new cover
        # photo was saved, so it kept the old cover. Since task 2.5 the album
        # starts only after the new cover is saved AND checked.
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.finish()
        self.say("button", "cover_no")
        order_id = self.db.orders[0]["id"]
        self.orders.answer(PHONE, "button", "edit_cover", TEXTS)
        replies, job = self.orders.answer(PHONE, "photo", photo(20), TEXTS)
        self.assertIn("בודקים", replies[0]["text"])
        self.assertEqual(len(self.ready), 1)               # not built yet
        self.assertEqual(self.covers, [(PHONE, order_id, job[1])])
        self.assertFalse(self.orders.wait_for_photos(order_id, 0.01, number=job[1]))
        self.orders.photo_done(order_id, job[1])           # bot.py calls this once it's saved
        self.assertTrue(self.orders.wait_for_photos(order_id, 0.01, number=job[1]))
        replies = self.check_covers()
        self.assertEqual(self.ready[-1], (PHONE, order_id))  # now the album is built
        self.assertEqual(len(self.ready), 2)
        self.assertEqual(self.db.orders[0]["step"], "done")
        self.assertIn(f"cover_photo:{job[1]}", self.db.orders[0]["notes"])

    def test_small_cover_photo_kept(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        replies = self.say("photo", photo(1), cover=SMALL_COVER)
        self.assertIn("HD", replies[-1]["text"])
        self.assertEqual(self.db.orders[0]["step"], "cover_problem")
        self.say("button", "cover_keep")
        self.assertIn("cover_kept", self.db.orders[0]["notes"])
        self.assertIn("cover_photo:1", self.db.orders[0]["notes"])

    def test_cover_check_restarts_after_a_bot_restart(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.orders.answer(PHONE, "photo", photo(1), TEXTS)   # the Mac turns off mid-check
        covers = []
        restarted = orders.Orders(self.db, on_cover=lambda *a: covers.append(a))
        replies, _ = restarted.answer(PHONE, "text", "נו?", TEXTS)
        self.assertIn("עוד רגע", replies[0]["text"])
        self.assertEqual(covers, [(PHONE, self.db.orders[0]["id"], 1)])
        restarted.answer(PHONE, "text", "נו?", TEXTS)
        self.assertEqual(len(covers), 1)                       # started once

    def test_wait_for_photos(self):
        self.orders.photo_saving("o1")
        self.assertFalse(self.orders.wait_for_photos("o1", timeout=0.01))
        self.orders.photo_done("o1")
        self.assertTrue(self.orders.wait_for_photos("o1", timeout=0.01))


if __name__ == "__main__":
    unittest.main()


class PhotoSizeTest(unittest.TestCase):
    """Task 1.2b: the bot reads each saved photo's size to ask about HD early."""

    def test_reads_jpeg_and_png_sizes(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("needs Pillow")
        import io
        for kind in ("JPEG", "PNG"):
            data = io.BytesIO()
            Image.new("RGB", (1536, 2048)).save(data, kind)
            self.assertEqual(orders.image_long_side(data.getvalue()), 2048)

    def test_unknown_is_none(self):
        self.assertIsNone(orders.image_long_side(b"photo bytes"))
        self.assertIsNone(orders.image_long_side(b""))
        self.assertIsNone(orders.image_long_side(b"\xff\xd8\xff"))

    def test_mostly_without_hd(self):
        o = orders.Orders(FakeDatabase())
        self.assertFalse(o.mostly_without_hd("order"))          # nothing known yet
        for n in range(1, 3):
            o.photo_size("order", n, 2048)
        self.assertFalse(o.mostly_without_hd("order"))          # too few to judge
        o.photo_size("order", 3, 4032)
        self.assertTrue(o.mostly_without_hd("order"))           # 2 of 3
        o.photo_size("order", 4, 4032)
        o.photo_size("order", 5, None)                          # unreadable: not counted
        self.assertTrue(o.mostly_without_hd("order"))           # 2 of 4 = half
        o.photo_size("order", 6, 5120)
        self.assertFalse(o.mostly_without_hd("order"))

    def test_count_asks_about_hd_once_photos_stop(self):
        orders.QUIET_SECONDS = 0.2
        try:
            db, sent = FakeDatabase(), []
            o = orders.Orders(db, on_cover=lambda *a: None)
            o.send = lambda phone, message: sent.append(message)
            o.answer(PHONE, "text", "שלום", TEXTS)
            o.answer(PHONE, "button", "design_classic", TEXTS)
            o.answer(PHONE, "photo", photo(1), TEXTS)    # the cover
            order_id = db.orders[0]["id"]
            o.photo_done(order_id, 1)
            o.cover_checked(PHONE, order_id, 1, GOOD_COVER, TEXTS)
            for n in range(2, 6):
                o.answer(PHONE, "photo", photo(n), TEXTS)
            for n in range(1, 6):   # like bot.py: each photo saved, its size known
                o.photo_size(order_id, n, 2048)
                o.photo_done(order_id, n)
            for _ in range(100):
                if sent:
                    break
                time.sleep(0.02)
            self.assertIn("HD", sent[-1]["text"])
            self.assertIn("קיבלנו 5 תמונות", sent[-1]["text"])
            self.assertEqual(db.orders[0]["step"], "hd_question")
        finally:
            orders.QUIET_SECONDS = 0
