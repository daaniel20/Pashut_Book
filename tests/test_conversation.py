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

    def test_button_titles_fit_whatsapp(self):
        # WhatsApp refuses button titles longer than 20 characters.
        for key in ["design_classic", "design_colorful", "button_photos_done",
                    "button_cover_yes", "button_cover_no"]:
            self.assertLessEqual(len(TEXTS[key]), 20, key)

    def test_reading_whatsapp_messages(self):
        read = conversation.read_message
        self.assertEqual(read({"type": "text", "text": {"body": "hi"}}), ("text", "hi"))
        self.assertEqual(read({"type": "image", "image": {}}), ("photo", None))
        self.assertEqual(read({"type": "document", "document": {"mime_type": "image/jpeg"}}),
                         ("photo", None))
        self.assertEqual(read({"type": "interactive",
                               "interactive": {"button_reply": {"id": "cover_no"}}}),
                         ("button", "cover_no"))
        self.assertEqual(read({"type": "video"}), ("other", "video"))


if __name__ == "__main__":
    unittest.main()
