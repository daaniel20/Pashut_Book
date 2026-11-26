"""Automatic checks for the order history (task 3.3).

A pretend Supabase (from test_orders.py) that keeps the history rows in a list.
Run:   python3 -m unittest discover tests
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import album_job  # noqa: E402
import cover_check  # noqa: E402
import history  # noqa: E402
import orders  # noqa: E402
import owner_approval  # noqa: E402
from database import DatabaseError  # noqa: E402
from settings import load_texts  # noqa: E402
from test_orders import FakeDatabase, FakeWhatsApp, photo  # noqa: E402

TEXTS = load_texts("he")
CUSTOMER = "972500000000"
GOOD_COVER = {"ok": True, "problem": None, "dpi": 300, "without_hd": False}


def setUpModule():
    global _real_few, _real_quiet
    _real_few = orders.conversation.FEW_PHOTOS
    _real_quiet = orders.QUIET_SECONDS
    orders.conversation.FEW_PHOTOS = 2
    orders.QUIET_SECONDS = 0


def tearDownModule():
    orders.conversation.FEW_PHOTOS = _real_few
    orders.QUIET_SECONDS = _real_quiet


class Database(FakeDatabase):
    def __init__(self):
        super().__init__()
        self.events = []
        self.history_down = False

    def add_event(self, row):
        if self.history_down:
            raise DatabaseError('Supabase error 404 on POST /rest/v1/order_events: '
                                'relation "public.order_events" does not exist')
        json.dumps(row)   # must be plain data, as sent to Supabase
        self.events.append(row)

    def get_order(self, order_id):
        return next((dict(o) for o in self.orders if o["id"] == order_id), None)

    def orders_with_note(self, note):
        return [dict(o) for o in self.orders if note in o["notes"]]


class ChangesTest(unittest.TestCase):
    def test_a_new_step_and_new_notes(self):
        rows = history.changes("photos", ["counted:3"], "cover",
                               ["counted:3", "counted:5", "used_title:2",
                                "cover_problem:small", "owner_token:abc123",
                                "owner_msgs:2026-11-26:2", "replaced:3:57"])
        self.assertEqual(rows, [
            ("step", None, "cover", {"from": "photos"}),
            ("counted", 5, None, {}),
            ("used_title", 2, None, {}),
            ("cover_problem", None, "small", {}),
            ("owner_msgs", 2, None, {}),       # the date is dropped
            ("replaced", None, "3:57", {}),
        ])   # the owner's secret code is not recorded

    def test_nothing_changed(self):
        self.assertEqual(history.changes("done", ["a"], "done", ["a"]), [])


class HistoryTest(unittest.TestCase):
    def test_missing_table_never_stops_the_bot(self):
        db = Database()
        db.history_down = True
        h = history.History(db, background=False)
        with self.assertLogs("bot", "WARNING") as logs:
            h.record("order-1", "step", detail="design")
            h.record("order-1", "step", detail="photos")
        self.assertEqual(len(logs.output), 1)   # said once, not for every row
        self.assertIn("3.3-order-history.sql", logs.output[0])

    def test_background_writing(self):
        db = Database()
        h = history.History(db)
        for n in range(5):
            h.record("order-1", "photo_saved", count=n + 1, info={"kb": 900})
        h.wait()
        self.assertEqual([r["count"] for r in db.events], [1, 2, 3, 4, 5])
        self.assertEqual(db.events[0]["info"], {"kb": 900})
        self.assertTrue(db.events[0]["created_at"])

    def test_orders_without_history_still_work(self):
        db = Database()
        o = orders.Orders(db)   # no history set (e.g. old tests, try_conversation.py)
        o.answer(CUSTOMER, "text", "שלום", TEXTS)
        self.assertEqual(db.events, [])


class JourneyTest(unittest.TestCase):
    """A whole order, from "hello" to "paid": every moment gets a row."""

    def setUp(self):
        self.db = Database()
        self.orders = orders.Orders(self.db)
        self.orders.history = history.History(self.db, background=False)
        self.sent = []
        self.covers = []
        self.orders.on_cover = lambda *a: self.covers.append(a)
        self.ready = []
        self.orders.on_ready = lambda *a: self.ready.append(a)
        self.approvals = owner_approval.OwnerApprovals(
            self.orders, self.send, TEXTS, "050-123-4567", "https://x",
            run_print=lambda order_id: {"problems": ["p"], "warnings": ["a", "b"], "notes": []})
        self.orders.on_approval = lambda phone, order_id: self.approvals.ask(phone, order_id)
        self.orders.on_payment = self.approvals.send_payment_request
        self._real_current = owner_approval.preview_links.current
        owner_approval.preview_links.current = lambda folder: (None, None)

    def tearDown(self):
        owner_approval.preview_links.current = self._real_current

    def send(self, phone, message):
        self.sent.append((phone, message))
        return True

    def say(self, kind, value=None):
        replies, job = self.orders.answer(CUSTOMER, kind, value, TEXTS)
        if job:   # like bot.py
            order_id, number = job
            orders.save_photo(self.db, FakeWhatsApp(), order_id, number, value,
                              record=lambda event, **v: self.orders.record(order_id, event, **v))
            self.orders.photo_done(order_id, number)
            while self.covers:   # like cover_check.py
                phone, oid, n = self.covers.pop(0)
                checks = cover_check.CoverChecks(self.orders, self.send, TEXTS,
                                                 run_tool=lambda *a: GOOD_COVER)
                checks.run(phone, oid, n)
        return replies

    def events(self, name=None):
        return [r for r in self.db.events if name is None or r["event"] == name]

    def test_every_moment_of_an_order(self):
        self.say("text", "שלום")
        order_id = self.db.orders[0]["id"]
        self.say("button", "design_classic")
        self.say("photo", photo(1))          # the cover photo
        for n in range(2, 6):
            self.say("photo", photo(n))
        self.say("button", "photos_done")
        self.say("button", "cover_yes")
        self.say("text", "סבתא שרה")
        self.assertEqual(self.ready, [(CUSTOMER, order_id)])

        # The album is built (a pretend album tool).
        def tool(oid, check_only):
            if check_only:
                return {"photos": 5, "used": 5, "without_hd": 0,
                        "left_out": {"blurry": 0, "duplicate": 0, "unusable": 0}}
            return {"pages": 20, "folder": "x", "design": "classic", "photos_in_album": 4,
                    "full_pages": 2, "photos_on_pages": 4, "notes": [],
                    "left_out": {"blurry": 0, "duplicate": 0, "unusable": 0},
                    "previews": [{"file": "p0.jpg"}]}
        album_job.AlbumJobs(self.orders, self.send, TEXTS, run_tool=tool,
                            make_link=lambda r: "https://x/album/C").run(CUSTOMER, order_id)

        # A change from the list, then "love it", the owner approves, shipping, payment.
        self.say("button", "edit_menu")
        self.say("button", "edit_title")
        self.say("text", "סבתא שרה 2026")
        self.say("button", "preview_ok")
        token = next(n for n in self.db.orders[0]["notes"] if n.startswith("owner_token:"))
        self.approvals.handle("button", f"owner_ok:{order_id}:{token.split(':')[1]}")
        for text in ("דנה כהן", "הרצל 5", "תל אביב", "0501112222"):
            self.say("text", text)
        self.say("button", "address_ok")
        self.approvals.handle("button", f"owner_paid:{order_id}")

        steps = [r["detail"] for r in self.events("step")]
        self.assertEqual(steps[:6], ["design", "cover_photo", "cover_check", "photos",
                                     "cover", "title"])
        self.assertEqual(steps[-8:], ["done", "ship_name", "ship_street", "ship_city",
                                      "ship_phone", "address_check", "payment", "paid"])
        names = [r["event"] for r in self.events()]
        self.assertEqual(names[0], "order_started")
        for name in ("photo_saved", "cover_checked", "album_checked", "album_built",
                     "previews_sent", "changing", "used_title", "preview_ok", "owner_asked",
                     "approved", "payment_wait", "paid"):
            self.assertIn(name, names)
        self.assertEqual(len(self.events("photo_saved")), 5)
        saved = self.events("photo_saved")[0]
        self.assertEqual((saved["count"], saved["detail"]), (1, "jpeg"))
        self.assertIn("seconds", saved["info"])
        self.assertEqual(self.events("cover_checked")[0]["detail"], "ok")
        built = self.events("album_built")[0]
        self.assertEqual((built["count"], built["detail"]), (20, "classic"))
        self.assertEqual(built["info"]["full_pages"], 2)
        self.assertEqual(built["step"], "done")
        self.assertEqual(built["photos"], 5)
        asked = self.events("owner_asked")[0]
        self.assertEqual((asked["info"]["problems"], asked["info"]["warnings"]), (1, 2))
        self.assertTrue(all(r["order_id"] == order_id for r in self.events()))

        # Numbers and codes only: no title, no name, no address, no phone number.
        everything = json.dumps(self.db.events, ensure_ascii=False)
        for private in ("סבתא", "דנה", "הרצל", "תל אביב", "0501112222", "111-2222",
                        CUSTOMER, token.split(":")[1]):
            self.assertNotIn(private, everything)

    def test_starting_over_is_recorded_on_both_orders(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        old = self.db.orders[0]["id"]
        self.say("text", "אלבום חדש")
        self.say("button", "restart_yes")
        new = self.db.orders[1]["id"]
        left = self.events("new_album")
        self.assertEqual([(r["order_id"], r["detail"]) for r in left], [(old, "cancelled")])
        started = [r["order_id"] for r in self.events("order_started")]
        self.assertEqual(started, [old, new])

    def test_a_bot_restart_records_no_old_moments_again(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        count = len(self.events())
        again = orders.Orders(self.db)
        again.history = self.orders.history
        again.answer(CUSTOMER, "photo", photo(1), TEXTS)
        new = [r for r in self.events()[count:] if r["event"] != "message_in"]
        self.assertEqual([(r["event"], r["detail"]) for r in new],
                         [("step", "cover_check"), ("cover_check", None)][:len(new)])
        self.assertEqual(new[0]["info"], {"from": "cover_photo"})


if __name__ == "__main__":
    unittest.main()
