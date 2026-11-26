"""Automatic checks for the behaviour data (task 3.3b).

Run:   python3 -m unittest discover tests
"""

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import behaviour  # noqa: E402
import bot  # noqa: E402
import history  # noqa: E402
import orders  # noqa: E402
import preview_links  # noqa: E402
from database import DatabaseError  # noqa: E402
from settings import load_texts  # noqa: E402
from test_history import Database  # noqa: E402
from test_orders import photo  # noqa: E402

TEXTS = load_texts("he")
CUSTOMER = "972500000000"
FAMILY = "972521234567"


class CustomerKeyTest(unittest.TestCase):
    def test_same_phone_same_key_but_not_the_number(self):
        key = behaviour.customer_key(CUSTOMER, "secret")
        self.assertEqual(key, behaviour.customer_key("+972 50-000-0000", "secret"))
        self.assertEqual(len(key), 16)
        self.assertNotIn("500000000", key)
        self.assertNotEqual(key, behaviour.customer_key(FAMILY, "secret"))
        self.assertNotEqual(key, behaviour.customer_key(CUSTOMER, "another secret"))
        self.assertIsNone(behaviour.customer_key(CUSTOMER, None))

    def test_the_secret_is_made_once_and_kept_in_env(self):
        with tempfile.TemporaryDirectory() as folder:
            env_file = Path(folder) / ".env"
            env_file.write_text("OWNER_PHONE=050\n", encoding="utf-8")
            env = {}
            secret = behaviour.key_secret(env, env_file)
            self.assertEqual(len(secret), 64)
            self.assertIn(f"CUSTOMER_KEY_SECRET={secret}", env_file.read_text(encoding="utf-8"))
            self.assertEqual(behaviour.key_secret(env, env_file), secret)   # not made again
            self.assertEqual(env_file.read_text(encoding="utf-8").count("CUSTOMER_KEY"), 1)

    def test_the_bots_version(self):
        version = behaviour.bot_version()
        self.assertRegex(version, r"^(\d{4}-\d\d-\d\d\.)?[0-9a-f]{7,}$|^unknown$")
        self.assertIsNone(behaviour._commit_from_files(Path("/no/such/folder")))

    def test_test_phones(self):
        phones = behaviour.test_phones({"OWNER_PHONE": "050-111-2222",
                                        "TEST_PHONES": "052-123-4567, +972 54 000 0000,"})
        self.assertEqual(phones, {"972501112222", FAMILY, "972540000000"})


class SourceTest(unittest.TestCase):
    def text(self, body, **more):
        return dict({"type": "text", "text": {"body": body}}, **more)

    def test_a_code_in_our_link(self):
        self.assertEqual(behaviour.read_source(self.text("שלום, אשמח לאלבום #FB1")),
                         ("fb1", None))

    def test_a_number_code(self):
        self.assertEqual(behaviour.read_source(self.text("שלום, אשמח לאלבום #204")),
                         ("204", None))

    def test_no_code(self):
        self.assertEqual(behaviour.read_source(self.text("שלום")), (None, None))
        self.assertEqual(behaviour.read_source(self.text("סבתא #1")), (None, None))
        self.assertEqual(behaviour.read_source(self.text("כיתה #12")), (None, None))
        self.assertEqual(behaviour.read_source({"type": "image"}), (None, None))

    def test_a_click_on_a_meta_ad(self):
        code, details = behaviour.read_source(self.text("שלום", referral={
            "source_type": "ad", "source_id": "1201", "media_type": "image",
            "headline": "אלבום", "source_url": "https://fb.me/x", "ctwa_clid": "abc"}))
        self.assertEqual(code, "ad")
        self.assertEqual(details, {"type": "ad", "ad_id": "1201", "media": "image",
                                   "from_ad": True})


    def test_our_link_gives_its_code_back(self):
        import source_link
        from urllib.parse import unquote
        link = source_link.make_link("972501234567", "flyer_tlv")
        self.assertTrue(link.startswith("https://wa.me/972501234567?text="))
        text = unquote(link.split("text=", 1)[1])
        self.assertEqual(behaviour.read_source(self.text(text)), ("flyer_tlv", None))
        # A number code, inside the invisible left-to-right marks.
        text = unquote(source_link.make_link("972501234567", "101").split("text=", 1)[1])
        self.assertTrue(text.endswith("\n\u2066(#101)\u2069"))
        self.assertEqual(behaviour.read_source(self.text(text)), ("101", None))


class MessageNameTest(unittest.TestCase):
    def test_names(self):
        t = TEXTS
        self.assertEqual(behaviour.message_name({"text": t["welcome"]}, t), "welcome")
        self.assertEqual(behaviour.message_name(
            {"text": t["photos_count"].format(photos="5 תמונות"), "buttons": []}, t),
            "photos_count")
        self.assertEqual(behaviour.message_name(
            {"text": "✅ שם: דנה\n\n" + t["ask_ship_street"]}, t), "ask_ship_street")
        self.assertEqual(behaviour.message_name({"text": "משהו אחר לגמרי"}, t), "other")
        self.assertEqual(behaviour.message_name({"image_file": "x.jpg"}, t), "image")

    def test_kinds(self):
        self.assertEqual(behaviour.message_kind({"text": "x"}), "text")
        self.assertEqual(behaviour.message_kind({"text": "x", "buttons": [1]}), "buttons")
        self.assertEqual(behaviour.message_kind({"text": "x", "link": {"url": "u"}, "image_file": "p"}),
                         "link")

    def test_expected(self):
        self.assertEqual(behaviour.expected("design"), "button")
        self.assertEqual(behaviour.expected("photos"), "photo")
        self.assertEqual(behaviour.expected("title"), "text")
        self.assertEqual(behaviour.expected("done", ["help_wait"]), "text")
        self.assertEqual(behaviour.button_code("owner_ok:abc:123"), "owner_ok")


class OutboxTest(unittest.TestCase):
    def test_delivered_then_read_once_each(self):
        box = behaviour.Outbox()
        box.add("wamid.1", CUSTOMER, "order-1", "welcome")
        later = time.time() + 30
        read = box.report("wamid.1", "read", str(int(later)))
        self.assertEqual((read["name"], read["order_id"]), ("welcome", "order-1"))
        self.assertAlmostEqual(read["seconds"], 30, delta=2)
        self.assertIsNone(box.report("wamid.1", "read"))      # Meta sent it twice
        self.assertIsNone(box.report("wamid.9", "delivered"))  # not ours / before a restart

    def test_only_the_newest_are_kept(self):
        box = behaviour.Outbox(size=2)
        for n in range(3):
            box.add(f"m{n}", CUSTOMER, "o", "x")
        self.assertIsNone(box.report("m0", "read"))
        self.assertIsNotNone(box.report("m2", "read"))


class PageNotesTest(unittest.TestCase):
    IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile/15E148"
    MAC = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) Safari/605.1.15"

    def test_open_and_seen(self):
        read = behaviour.PageNotes.read
        self.assertEqual(read({"e": "open", "d": "abc12345"}, self.IPHONE),
                         ("album_opened", None, "phone", {"device": "abc12345"}))
        self.assertEqual(read({"e": "open", "d": "abc12345", "o": 1}, self.MAC)[2], "owner")
        event, depth, kind, info = read({"e": "seen", "d": "abc12345", "depth": 250,
                                         "seconds": 40, "images_seen": 7, "images": 12},
                                        self.MAC)
        self.assertEqual((event, depth, kind), ("album_seen", 100, "computer"))
        self.assertEqual(info, {"device": "abc12345", "seconds": 40, "images_seen": 7,
                                "images": 12})

    def test_bad_notes_are_ignored(self):
        read = behaviour.PageNotes.read
        self.assertIsNone(read({"e": "open", "d": "<script>"}, self.MAC))
        self.assertIsNone(read({"e": "hack", "d": "abc12345"}, self.MAC))
        self.assertIsNone(read(["open"], self.MAC))

    def test_limit_per_link(self):
        notes = behaviour.PageNotes(per_hour=2)
        self.assertEqual([notes.allowed("c") for _ in range(3)], [True, True, False])
        self.assertTrue(notes.allowed("other"))

    def test_the_page_sends_its_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            links = Path(folder)
            code = preview_links.create(links / "album", [{"file": "00-cover.jpg", "pages": []}],
                                        2, links_dir=links, order_id="order-1")
            data = preview_links.find(code, links)
        self.assertEqual(data["order_id"], "order-1")
        page = preview_links.page_html(code, data, TEXTS)
        self.assertIn(f"/album/{code}/note", page)
        self.assertIn("sendBeacon", page)


class HistoryColumnsTest(unittest.TestCase):
    def test_every_row_has_key_test_mark_and_version(self):
        db = Database()
        h = history.History(db, background=False, key_secret="s",
                            test_phones={FAMILY}, version="2026-11-26.abc1234")
        h.record("order-1", "x", phone=CUSTOMER)
        h.record("order-2", "x", phone=FAMILY)
        h.record("order-1", "y")   # the phone is remembered
        rows = db.events
        self.assertEqual(rows[0]["customer"], behaviour.customer_key(CUSTOMER, "s"))
        self.assertEqual([r["test"] for r in rows], [False, True, False])
        self.assertEqual(rows[2]["customer"], rows[0]["customer"])
        self.assertEqual(rows[0]["version"], "2026-11-26.abc1234")
        self.assertNotIn(CUSTOMER, json.dumps(rows))

    def test_an_unknown_order_is_looked_up_once(self):
        db = Database()
        db.orders.append({"id": "order-7", "phone": FAMILY, "notes": []})
        h = history.History(db, background=False, key_secret="s", test_phones={FAMILY})
        h.record("order-7", "album_opened")
        self.assertTrue(db.events[0]["test"])
        self.assertEqual(db.events[0]["customer"], behaviour.customer_key(FAMILY, "s"))

    def test_before_the_new_columns_exist(self):
        class Old(Database):
            def add_event(self, row):
                if "customer" in row:
                    raise DatabaseError("Supabase error 400 on POST /rest/v1/order_events: "
                                        "Could not find the 'customer' column of "
                                        "'order_events' in the schema cache")
                super().add_event(row)
        db = Old()
        h = history.History(db, background=False, key_secret="s")
        with self.assertLogs("bot", "WARNING") as logs:
            h.record("order-1", "x", phone=CUSTOMER)
            h.record("order-1", "y")
        self.assertEqual([r["event"] for r in db.events], ["x", "y"])
        self.assertEqual(len(logs.output), 1)
        self.assertIn("3.3b-behaviour-data.sql", logs.output[0])


class IncomingMessagesTest(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        self.orders = orders.Orders(self.db)
        self.orders.history = history.History(self.db, background=False)

    def say(self, kind, value=None, source=None):
        return self.orders.answer(CUSTOMER, kind, value, TEXTS, source=source)

    def messages(self):
        return [r for r in self.db.events if r["event"] == "message_in"]

    def test_every_message_is_recorded_without_its_text(self):
        self.say("text", "שלום, אשמח לאלבום")
        self.say("text", "קלאסי בבקשה כן")       # typed instead of tapping a design
        self.say("button", "design_classic")
        self.say("photo", photo(1))
        rows = self.messages()
        self.assertEqual([r["detail"] for r in rows], ["text", "text", "button", "photo"])
        self.assertEqual(rows[0]["info"]["expected"], "any")
        self.assertTrue(rows[0]["info"]["changed"])
        self.assertEqual(rows[0]["info"]["replies"], ["welcome", "choose_design"])
        confused = rows[1]
        self.assertEqual((confused["step"], confused["info"]["expected"]), ("design", "button"))
        self.assertFalse(confused["info"]["changed"])
        self.assertTrue(confused["info"]["confused"])
        self.assertEqual(confused["info"]["letters"], len("קלאסי בבקשה כן"))
        self.assertEqual(rows[2]["info"]["button"], "design_classic")
        self.assertFalse(rows[2]["info"]["confused"])
        self.assertTrue(rows[3]["info"]["changed"])
        self.assertNotIn("שלום", json.dumps(self.db.events, ensure_ascii=False))

    def test_page_visits_get_the_step_and_photo_count(self):
        self.say("text", "שלום")
        order_id = self.db.orders[0]["id"]
        self.orders.record(order_id, "album_opened", detail="phone")
        row = self.db.events[-1]
        self.assertEqual((row["step"], row["photos"]), ("design", 0))

    def test_the_source_is_recorded_and_carried_to_a_new_album(self):
        self.say("text", "שלום #fb1", source=("fb1", None))
        first = self.db.orders[0]["id"]
        self.say("button", "design_classic")
        self.say("text", "אלבום חדש")
        self.say("button", "restart_yes")
        second = self.db.orders[1]["id"]
        sources = [(r["order_id"], r["detail"]) for r in self.db.events if r["event"] == "source"]
        self.assertEqual(sources, [(first, "fb1"), (second, "fb1")])


class LinkMessageTest(unittest.TestCase):
    """Owner's phone test (Nov 26, 2026): our link's first message, sent by a
    customer whose album was already paid, went to the owner."""

    def setUp(self):
        self.db = Database()
        self.orders = orders.Orders(self.db)
        self.orders.history = history.History(self.db, background=False)

    def say(self, kind, value, source=None):
        return self.orders.answer(CUSTOMER, kind, value, TEXTS, source=source)

    def test_after_a_paid_album_a_new_album_starts(self):
        self.say("text", "שלום")
        self.orders._states[CUSTOMER]["step"] = "paid"
        passed = []
        self.orders.on_customer_text = lambda *a: passed.append(a)
        replies = self.say("text", "שלום! אשמח להכין אלבום תמונות\n(#101)", source=("101", None))[0]
        self.assertEqual(passed, [])                       # not sent to the owner
        self.assertEqual(len(self.db.orders), 2)           # a new album
        self.assertNotEqual(self.db.orders[0].get("status"), "cancelled")   # the paid one kept
        self.assertEqual([behaviour.message_name(r, TEXTS) for r in replies],
                         ["welcome", "choose_design"])

    def test_in_the_middle_it_is_not_taken_as_an_answer(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        state = self.orders._states[CUSTOMER]
        state["step"] = "title"
        replies = self.say("text", "שלום! אשמח להכין אלבום תמונות\n(#101)", source=("101", None))[0]
        self.assertIsNone(state["title"])                  # not saved as the cover title
        self.assertEqual(state["step"], "title")
        self.assertEqual(behaviour.message_name(replies[0], TEXTS), "ask_title")
        self.assertNotIn("from_link", state)

    def test_an_ordinary_text_is_unchanged(self):
        self.say("text", "שלום")
        self.say("button", "design_classic")
        self.orders._states[CUSTOMER]["step"] = "title"
        self.say("text", "סבתא שרה")
        self.assertEqual(self.orders._states[CUSTOMER]["title"], "סבתא שרה")


class SentMessagesTest(unittest.TestCase):
    """bot.py: sent messages and their delivered / read reports."""

    def setUp(self):
        self.db = Database()
        self.orders = orders.Orders(self.db)
        self.orders.history = history.History(self.db, background=False)
        self.orders.answer(CUSTOMER, "text", "שלום", TEXTS)
        self.saved = (bot.orders, bot.outbox)
        bot.orders, bot.outbox = self.orders, behaviour.Outbox()

    def tearDown(self):
        bot.orders, bot.outbox = self.saved

    def test_sent_delivered_read(self):
        bot.record_sent(CUSTOMER, {"text": TEXTS["welcome"]}, "wamid.1")
        bot.record_sent("972509999999", {"text": TEXTS["welcome"]}, "wamid.2")   # no order
        bot.record_status({"id": "wamid.1", "status": "sent"})
        bot.record_status({"id": "wamid.1", "status": "delivered"})
        bot.record_status({"id": "wamid.1", "status": "read"})
        bot.record_status({"id": "wamid.1", "status": "read"})
        rows = [(r["event"], r["detail"]) for r in self.db.events
                if r["event"].startswith("message_") and r["event"] != "message_in"]
        self.assertEqual(rows, [("message_out", "welcome"), ("message_delivered", "welcome"),
                                ("message_read", "welcome")])

    def test_the_owners_messages_are_not_recorded(self):
        bot.record_sent(CUSTOMER, {"text": TEXTS["owner_decide"]}, "wamid.3")
        self.assertFalse([r for r in self.db.events if r["event"] == "message_out"])


if __name__ == "__main__":
    unittest.main()
