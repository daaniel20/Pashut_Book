"""Automatic checks for the customer conversation (task 1.2).

Run:   python3 -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import conversation  # noqa: E402
from settings import load_texts  # noqa: E402

TEXTS = load_texts("he")


def talk(state, kind, value=None):
    return conversation.answer(state, kind, value, TEXTS)


def button_ids(message):
    return [button["id"] for button in message.get("buttons", [])]


class ConversationTest(unittest.TestCase):
    def test_full_happy_path(self):
        state = conversation.new_state()
        replies = talk(state, "text", "היי")
        self.assertEqual(len(replies), 2)
        self.assertEqual(button_ids(replies[1]), ["design_classic", "design_colorful"])

        replies = talk(state, "button", "design_colorful")
        self.assertEqual(state["step"], "photos")
        self.assertIn("HD", replies[0]["text"])

        first = talk(state, "photo")
        self.assertEqual(button_ids(first[0]), ["photos_done"])
        for _ in range(59):
            self.assertEqual(talk(state, "photo"), [])  # quiet, no reply per photo
        self.assertEqual(state["photos"], 60)

        replies = talk(state, "button", "photos_done")
        self.assertIn("60", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["cover_yes", "cover_no"])

        talk(state, "button", "cover_yes")
        self.assertEqual(state["step"], "title")
        replies = talk(state, "text", "  סבתא  ונכדים 2026 ")
        self.assertEqual(state["title"], "סבתא ונכדים 2026")
        self.assertEqual(state["step"], "done")
        self.assertIn("צבעוני", replies[0]["text"])

        self.assertEqual(len(talk(state, "text", "מה קורה?")), 1)
        self.assertEqual(talk(state, "text", "?"), [])  # said once, then quiet

    def test_wrong_input_repeats_the_question(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        replies = talk(state, "text", "לא יודעת")
        self.assertEqual(state["step"], "design")
        self.assertEqual(button_ids(replies[0]), ["design_classic", "design_colorful"])
        talk(state, "text", "קלאסי")  # typing the name also works
        self.assertEqual(state["design"], "classic")

    def test_done_without_photos(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "text", "סיימתי")
        self.assertEqual(state["step"], "photos")

    def test_photos_before_design_are_counted_with_one_reminder(self):
        state = conversation.new_state()
        self.assertEqual(len(talk(state, "photo")), 2)  # welcome + design buttons
        for _ in range(9):
            self.assertEqual(talk(state, "photo"), [])
        self.assertEqual(state["photos"], 10)
        replies = talk(state, "button", "design_classic")
        self.assertIn("10", replies[1]["text"])

    def test_photo_limit(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(conversation.MAX_PHOTOS):
            talk(state, "photo")
        self.assertEqual(len(talk(state, "photo")), 1)  # "that's the maximum"
        self.assertEqual(talk(state, "photo"), [])
        self.assertEqual(state["photos"], conversation.MAX_PHOTOS)

    def test_typed_title_and_too_long_title(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "text", "זהו")
        talk(state, "text", "א" * 50)  # typed instead of tapping: treated as a title
        self.assertEqual(state["step"], "title")
        talk(state, "text", "החתונה של דנה")
        self.assertEqual(state["title"], "החתונה של דנה")

    def test_no_title_and_restart(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        self.assertEqual(state["step"], "done")
        self.assertIsNone(state["title"])
        talk(state, "text", "אלבום חדש")
        self.assertEqual(state["step"], "design")
        self.assertEqual(state["photos"], 0)

    def finished_order(self, title_button="cover_no"):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", title_button)
        return state

    def test_summary_has_change_buttons(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        replies = talk(state, "button", "cover_no")
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design"])

    def test_add_a_title_after_choosing_none(self):
        state = self.finished_order()
        replies = talk(state, "button", "edit_title")
        self.assertEqual(state["step"], "title")
        self.assertEqual(button_ids(replies[0]), ["cover_no"])
        replies = talk(state, "text", "יום הולדת לסבתא")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["title"], "יום הולדת לסבתא")
        self.assertIn("יום הולדת לסבתא", replies[0]["text"])
        self.assertNotIn("editing", state["notes"])

    def test_remove_a_title(self):
        state = self.finished_order()
        talk(state, "button", "edit_title")
        talk(state, "text", "החופשה")
        talk(state, "button", "edit_title")
        talk(state, "button", "cover_no")
        self.assertEqual(state["step"], "done")
        self.assertIsNone(state["title"])

    def test_change_design_goes_straight_back_to_the_summary(self):
        state = self.finished_order()
        replies = talk(state, "button", "edit_design")
        self.assertEqual(button_ids(replies[0]), ["design_classic", "design_colorful"])
        replies = talk(state, "button", "design_colorful")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["design"], "colorful")
        self.assertEqual(state["photos"], 1)  # photos are kept
        self.assertIn("צבעוני", replies[0]["text"])

    def test_text_after_done_offers_the_change_buttons(self):
        state = self.finished_order()
        replies = talk(state, "text", "תודה")
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design"])

    def test_button_titles_fit_whatsapp(self):
        # WhatsApp refuses button titles longer than 20 characters.
        for key in ["design_classic", "design_colorful", "button_photos_done",
                    "button_cover_yes", "button_cover_no",
                    "button_edit_title", "button_edit_design"]:
            self.assertLessEqual(len(TEXTS[key]), 20, key)

    def test_reading_whatsapp_messages(self):
        read = conversation.read_message
        self.assertEqual(read({"type": "text", "text": {"body": "hi"}}), ("text", "hi"))
        self.assertEqual(read({"type": "image", "image": {"id": "7", "mime_type": "image/jpeg"}}),
                         ("photo", {"id": "7", "mime_type": "image/jpeg"}))
        self.assertEqual(read({"type": "document",
                               "document": {"id": "8", "mime_type": "image/png"}}),
                         ("photo", {"id": "8", "mime_type": "image/png"}))
        self.assertEqual(read({"type": "interactive",
                               "interactive": {"button_reply": {"id": "cover_no"}}}),
                         ("button", "cover_no"))
        self.assertEqual(read({"type": "video"}), ("other", "video"))


class AlbumMessagesTest(unittest.TestCase):
    """Task 2.2: the HD question and the "photos left out" message."""

    def finished_state(self, photos=5):
        state = conversation.new_state()
        talk(state, "text", "היי")
        talk(state, "button", "design_classic")
        for _ in range(photos):
            talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_yes")
        talk(state, "text", "הטיול")
        self.assertEqual(state["step"], "done")
        return state

    def test_left_out_message(self):
        text = conversation.left_out_message({"blurry": 3, "duplicate": 2, "unusable": 0}, TEXTS)
        self.assertIn("3 תמונות מטושטשות ו-2 תמונות כפולות לא נכנסו", text)
        text = conversation.left_out_message({"blurry": 1, "duplicate": 0, "unusable": 0}, TEXTS)
        self.assertIn("תמונה מטושטשת אחת לא נכנסה", text)
        text = conversation.left_out_message({"blurry": 2, "duplicate": 1, "unusable": 4}, TEXTS)
        self.assertIn("2 תמונות מטושטשות, תמונה כפולה אחת ו-4 תמונות", text)
        self.assertIsNone(conversation.left_out_message(
            {"blurry": 0, "duplicate": 0, "unusable": 0}, TEXTS))

    def test_hd_question_buttons_fit_whatsapp(self):
        message = conversation.hd_question(TEXTS)
        self.assertEqual(button_ids(message), ["hd_help", "hd_continue"])
        for button in message["buttons"]:
            self.assertLessEqual(len(button["title"]), 20)   # WhatsApp's limit

    def test_continue_anyway(self):
        state = self.finished_state()
        state["step"] = "hd_question"        # what album_job.py does
        replies = talk(state, "button", "hd_continue")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["photos"], 5)
        self.assertEqual(len(replies), 1)

    def test_resend_in_hd_keeps_the_title(self):
        state = self.finished_state()
        state["step"] = "hd_question"
        replies = talk(state, "button", "hd_help")
        self.assertIn("HD", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        self.assertEqual((state["step"], state["photos"]), ("photos", 0))
        self.assertTrue(state.pop("resend_photos"))
        for _ in range(4):
            talk(state, "photo")
        replies = talk(state, "button", "photos_done")
        # The cover was already answered: straight to the summary.
        self.assertEqual(state["step"], "done")
        self.assertIn("הטיול", replies[0]["text"])
        self.assertIn("4", replies[0]["text"])

    def test_photo_instead_of_tapping_starts_the_resend(self):
        state = self.finished_state()
        state["step"] = "hd_question"
        replies = talk(state, "photo")
        self.assertEqual((state["step"], state["photos"]), ("photos", 1))
        self.assertTrue(state["resend_photos"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])

    def test_other_text_repeats_the_question(self):
        state = self.finished_state()
        state["step"] = "hd_question"
        replies = talk(state, "text", "מה?")
        self.assertEqual(button_ids(replies[0]), ["hd_help", "hd_continue"])


if __name__ == "__main__":
    unittest.main()
