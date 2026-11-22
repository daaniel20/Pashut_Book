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
        self.orders = orders.Orders(self.db)

    def say(self, kind, value=None):
        return self.orders.answer(PHONE, kind, value, TEXTS)

    def send_photos(self, count, start=1):
        for n in range(start, start + count):
            replies, job = self.say("photo", photo(n))
            if job:
                order_id, number = job
                orders.save_photo(self.db, FakeWhatsApp(), order_id, number, photo(n))

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
        old, new = self.db.orders
        self.assertEqual(old["status"], "cancelled")
        self.assertEqual(new["status"], "collecting")
        # The deletion runs on a timer; wait for it.
        for _ in range(100):
            if not self.db.files:
                break
            time.sleep(0.01)
        self.assertEqual(self.db.files, {})

    def test_finished_album_is_kept_when_starting_a_new_one(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.send_photos(2)
        self.say("button", "photos_done")
        self.say("button", "cover_no")
        self.assertEqual(self.db.orders[0]["status"], "ready")
        self.say("text", "אלבום חדש")
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


if __name__ == "__main__":
    unittest.main()
