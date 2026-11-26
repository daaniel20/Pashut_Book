"""Automatic checks for the owner's approval on WhatsApp (task 3.1).

A pretend Supabase (from test_orders.py), no WhatsApp and no print tool.
Run:   python3 -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import orders  # noqa: E402
import owner_approval  # noqa: E402
from settings import load_texts  # noqa: E402
from test_orders import FakeDatabase  # noqa: E402

TEXTS = load_texts("he")
CUSTOMER = "972500000000"
OWNER = "972501234567"
ORDER = "11111111-2222-3333-4444-555555555555"


class Database(FakeDatabase):
    def get_order(self, order_id):
        return next((dict(o) for o in self.orders if o["id"] == order_id), None)

    def orders_with_note(self, note):
        return [dict(o) for o in self.orders if note in o["notes"]]


def no_link(folder):
    return None, None


class OwnerApprovalTest(unittest.TestCase):
    def setUp(self):
        self.db = Database()
        # A finished album whose preview link the customer already got (task 2.4).
        self.db.orders.append({"id": ORDER, "phone": CUSTOMER, "status": "ready",
                               "step": "done", "design": "classic", "title": "סבתא",
                               "photo_count": 50, "notes": ["previews_sent"]})
        self.orders = orders.Orders(self.db)
        self.sent = []
        self.report = {"problems": [], "warnings": [], "notes": []}
        self.approvals = owner_approval.OwnerApprovals(
            self.orders, self.send, TEXTS, "050-123-4567", "https://x",
            run_print=lambda order_id: self.report)
        self.asked, self.told = [], []
        self.orders.on_approval = lambda *a: self.asked.append(a)
        self.orders.on_customer_text = lambda *a: self.told.append(a)
        self._real_current = owner_approval.preview_links.current
        owner_approval.preview_links.current = no_link

    def tearDown(self):
        owner_approval.preview_links.current = self._real_current

    def send(self, phone, message):
        self.sent.append((phone, message))
        return True

    def customer(self, kind, value):
        replies, _ = self.orders.answer(CUSTOMER, kind, value, TEXTS)
        return replies

    def owner(self, kind, value):
        """Like bot.py: the owner's message, if it's for the owner's part."""
        if self.approvals.handles(OWNER, kind, value):
            self.approvals.handle(kind, value)
            return True
        return False

    def to(self, phone):
        return [m for p, m in self.sent if p == phone]

    def love_it(self):
        self.customer("button", "preview_ok")
        self.assertEqual(self.asked, [(CUSTOMER, ORDER)])
        self.approvals.ask(CUSTOMER, ORDER)   # what start() does in the background
        return self.to(OWNER)[-1]["buttons"]

    def test_the_owner_number_in_any_form(self):
        for typed in ("050-123-4567", "+972 50 123 4567", "972501234567"):
            self.assertEqual(owner_approval.owner_number(typed), OWNER)
        self.assertIsNone(owner_approval.owner_number(""))

    def test_love_it_asks_the_owner(self):
        buttons = self.love_it()
        request = self.to(OWNER)[0]["text"]
        self.assertIn(ORDER[:8], request)
        self.assertIn("סבתא", request)
        self.assertIn("בלי בעיות", request)
        self.assertEqual([b["id"].split(":")[0] for b in buttons], ["owner_ok", "owner_problem"])
        self.assertIn("owner_check", self.db.orders[0]["notes"])
        self.assertEqual(self.to(CUSTOMER), [])   # nothing extra to the customer yet

    def test_the_request_shows_the_preview_link_and_print_checks(self):
        owner_approval.preview_links.current = lambda folder: (
            "CODE", {"pages": 22, "photos": 48, "images": [{"name": "00-cover.jpg"}]})
        self.report = {"problems": ["page 3: 007.jpg prints at only 120 DPI (will look blurry), "
                                    "use a smaller spot or another photo."],
                       "warnings": [f"page {n}: soft" for n in range(7)], "notes": []}
        self.love_it()
        request = self.to(OWNER)[0]
        self.assertEqual(request["link"]["url"], "https://x/album/CODE?o=1")   # the owner's visits are marked (3.3b)
        self.assertIn("22", request["text"])
        # One detail per line, in Hebrew (owner's test, task 1.2b).
        self.assertIn("\n📄 22 עמודים\n", request["text"])
        self.assertIn("❌ עמוד 3: תמונה 7 תצא מטושטשת", request["text"])
        self.assertNotIn("DPI", request["text"])
        self.assertNotIn("page", request["text"])
        # Photos at 150-199 DPI (e.g. without HD) print fine: one line, not a list.
        self.assertNotIn("soft", request["text"])
        self.assertIn("ℹ️ 7", request["text"])

    def test_many_problems_are_cut_short(self):
        self.report = {"problems": [f"page {n}: blurry" for n in range(8)],
                       "warnings": [], "notes": []}
        self.love_it()
        self.assertIn("…ועוד 3", self.to(OWNER)[0]["text"])   # at most 5 listed

    def test_approve(self):
        buttons = self.love_it()
        self.assertTrue(self.owner("button", buttons[0]["id"]))
        self.assertIn("מוכן להדפסה", self.to(CUSTOMER)[-1]["text"])
        self.assertIn("אושר", self.to(OWNER)[-1]["text"])
        notes = self.db.orders[0]["notes"]
        self.assertIn("approved", notes)
        self.assertNotIn("owner_check", notes)
        self.owner("button", buttons[0]["id"])   # tapped twice
        self.assertIn("כבר אושר", self.to(OWNER)[-1]["text"])
        self.assertEqual(len(self.to(CUSTOMER)), 1)

    def test_address_payment_and_paid(self):
        """Task 3.2: approve -> the customer's address -> a Bit request by the
        owner -> "payment received" -> the customer hears it goes to print."""
        self.orders.on_payment = self.approvals.send_payment_request
        buttons = self.love_it()
        self.owner("button", buttons[0]["id"])
        self.assertIn("השם המלא", self.to(CUSTOMER)[-1]["text"])
        row = self.db.orders[0]
        self.assertEqual((row["step"], row["status"]), ("ship_name", "approved"))
        self.customer("text", "דנה כהן")
        self.customer("text", "הרצל 5")
        self.customer("text", "תל אביב")
        self.customer("text", "0501112222")
        self.customer("button", "address_ok")
        self.assertEqual((row["ship_name"], row["ship_street"], row["ship_city"],
                          row["ship_phone"]), ("דנה כהן", "הרצל 5", "תל אביב", "050-111-2222"))
        self.assertEqual(row["price"], 180)
        request = self.to(OWNER)[-1]
        self.assertIn("050-000-0000", request["text"])   # the full number, for Bit
        self.assertIn("₪180", request["text"])
        self.assertIn("הרצל 5", request["text"])
        paid = request["buttons"][0]["id"]
        self.assertEqual(paid, f"owner_paid:{ORDER}")

        # "אישורים" sends it again (e.g. after the 24-hour window closed).
        self.owner("text", "אישורים")
        self.assertEqual(self.to(OWNER)[-1]["buttons"][0]["id"], paid)

        self.owner("button", paid)
        self.assertIn("התשלום התקבל", self.to(CUSTOMER)[-1]["text"])
        self.assertIn("נרשם", self.to(OWNER)[-1]["text"])
        self.assertEqual((row["step"], row["status"]), ("paid", "paid"))
        self.assertIn("paid_at", row)
        self.owner("button", paid)                       # tapped twice
        self.assertIn("כבר נרשם", self.to(OWNER)[-1]["text"])

        # After a bot restart, the address and price are still known.
        again = orders.Orders(self.db)
        self.assertEqual(again.info(CUSTOMER, ORDER)["ship"]["city"], "תל אביב")

        # Starting a new album keeps the paid one (it isn't cancelled).
        self.customer("text", "אלבום חדש")
        self.customer("button", "restart_yes")
        self.assertEqual(row["status"], "paid")

    def test_the_owner_sees_the_customers_photo_changes(self):
        self.db.orders[0]["notes"] += ["removed:4", "replaced:9:51"]
        self.love_it()
        self.assertIn("🗑️ 4, 📷 9→51", self.to(OWNER)[0]["text"])

    def test_the_photo_number_is_checked_against_the_album(self):
        self.orders.album_numbers = lambda order_id: {7, 8}
        self.customer("button", "edit_photo")
        self.assertIn("לא מצאנו", self.customer("text", "5")[0]["text"])
        self.customer("text", "7")
        self.assertEqual(self.db.orders[0]["step"], "photo_action")
        self.assertIn("photo_pick:7", self.db.orders[0]["notes"])

    def test_help_question_and_answer(self):
        self.orders.on_help = self.approvals.send_help
        self.customer("text", "עזרה")
        self.customer("text", "מתי האלבום יגיע?")
        request = self.to(OWNER)[-1]
        self.assertIn("מתי האלבום יגיע?", request["text"])
        self.assertEqual(request["buttons"][0]["id"], f"owner_help:{ORDER}")
        self.owner("button", request["buttons"][0]["id"])
        self.assertTrue(self.owner("text", "בעוד שבוע 🙂"))
        answer = self.to(CUSTOMER)[-1]
        self.assertIn("בעוד שבוע", answer["text"])
        self.assertNotIn("buttons", answer)          # a help answer has no buttons

    def test_local_number(self):
        self.assertEqual(owner_approval.local_number("972501234567"), "050-123-4567")
        self.assertEqual(owner_approval.local_number("447700900123"), "+447700900123")

    def test_an_old_request_after_a_change_does_nothing(self):
        buttons = self.love_it()
        self.customer("button", "edit_title")
        self.customer("text", "כותרת חדשה")
        self.owner("button", buttons[0]["id"])
        self.assertIn("השתנה", self.to(OWNER)[-1]["text"])
        self.assertNotIn("approved", self.db.orders[0]["notes"])

    def test_a_problem_sends_the_owners_message_to_the_customer(self):
        buttons = self.love_it()
        self.owner("button", buttons[1]["id"])
        self.assertIn("ביטול", self.to(OWNER)[-1]["text"])
        self.assertTrue(self.owner("text", "תמונה 12 מטושטשת, אפשר לשלוח אחרת?"))
        message = self.to(CUSTOMER)[-1]
        self.assertIn("תמונה 12 מטושטשת", message["text"])
        self.assertEqual(message["buttons"][0]["id"], "edit_menu")
        self.assertIn("טלפון מסתיים ב-000", self.to(OWNER)[-1]["text"])
        self.assertIn("owner_problem", self.db.orders[0]["notes"])
        # The owner's next text is their own again (e.g. as a test customer).
        self.assertFalse(self.owner("text", "שלום"))
        # They can still approve later from the same request.
        self.owner("button", buttons[0]["id"])
        self.assertIn("approved", self.db.orders[0]["notes"])

    def test_cancel_sends_nothing(self):
        buttons = self.love_it()
        self.owner("button", buttons[1]["id"])
        self.owner("text", "ביטול")
        self.assertEqual(self.to(CUSTOMER), [])

    def test_the_customers_text_goes_to_the_owner(self):
        self.love_it()
        self.customer("text", "מתי זה מגיע?")
        self.assertEqual(self.told, [(CUSTOMER, ORDER, "מתי זה מגיע?")])
        self.approvals.tell_owner(*self.told[0])
        message = self.to(OWNER)[-1]
        self.assertIn("מתי זה מגיע?", message["text"])
        ids = [b["id"].split(":")[0] for b in message["buttons"]]
        self.assertEqual(ids, ["owner_write", "owner_ok"])
        self.owner("button", message["buttons"][0]["id"])
        self.owner("text", "בעוד שבוע 🙂")
        self.assertIn("בעוד שבוע", self.to(CUSTOMER)[-1]["text"])

    def test_waiting_albums_again(self):
        self.owner("text", "אישורים")
        self.assertIn("אין אלבומים", self.to(OWNER)[-1]["text"])
        buttons = self.love_it()
        self.sent.clear()
        self.owner("text", "אישורים")
        self.assertEqual(self.to(OWNER)[-1]["buttons"], buttons)   # the same request

    def test_only_the_owner_and_only_owner_messages(self):
        buttons = self.love_it()
        self.assertFalse(self.approvals.handles(CUSTOMER, "button", buttons[0]["id"]))
        self.assertFalse(self.approvals.handles(OWNER, "button", "preview_ok"))
        self.assertFalse(self.approvals.handles(OWNER, "text", "אלבום חדש"))
        self.assertFalse(self.approvals.handles(OWNER, "photo", {"id": "1"}))

    def test_a_print_failure_is_shown_to_the_owner(self):
        self.report = {"error": "Photos missing for this album: photo 003"}
        self.love_it()
        self.assertIn("לא נוצרו", self.to(OWNER)[0]["text"])


if __name__ == "__main__":
    unittest.main()


class HebrewChecksTest(unittest.TestCase):
    """The print tool's English notes, as the owner reads them in WhatsApp."""

    def test_known_notes(self):
        t = TEXTS
        cases = {
            "cover: 012.jpg prints at only 120 DPI (will look blurry)": "כריכה: תמונה 12 תצא מטושטשת",
            "23 pages: the printer needs a multiple of 2.": "מספר העמודים (23) לא מתאים",
            "The customer's cover photo (004.jpg) can't be used (blurry or too small)": "נבחרה תמונה אחרת",
            "The cover photo (004.jpg) is too small or blurry to fill the cover (120 DPI edge "
            "to edge): it is shown smaller. Check the cover before printing.": "מוצגת קטנה יותר",
            "Only 12 usable photos: the album has 20 pages": "רק 12 תמונות טובות",
            "Something new": "bot.log",
        }
        for english, hebrew in cases.items():
            self.assertIn(hebrew, owner_approval.in_hebrew(english, t), english)
