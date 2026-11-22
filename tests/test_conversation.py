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
    """The IDs of a message's buttons, or of its list's choices."""
    rows = message["list"]["rows"] if "list" in message else message.get("buttons", [])
    return [row["id"] for row in rows]


# Most checks here are about other steps and send only a few photos, so the
# "only N photos, add more?" question (FewPhotosTest) is turned down for them.
def setUpModule():
    global _real_few
    _real_few = conversation.FEW_PHOTOS
    conversation.FEW_PHOTOS = 2


def tearDownModule():
    conversation.FEW_PHOTOS = _real_few


class ConversationTest(unittest.TestCase):
    def test_full_happy_path(self):
        state = conversation.new_state()
        replies = talk(state, "text", "היי")
        self.assertEqual(len(replies), 2)
        self.assertEqual(button_ids(replies[1]), ["design_classic", "design_colorful"])

        replies = talk(state, "button", "design_colorful")
        self.assertEqual(state["step"], "cover_photo")
        self.assertIn("HD", replies[0]["text"])
        self.assertIn("כריכה", replies[0]["text"])

        first = talk(state, "photo")             # the cover photo
        self.assertIn("40", first[0]["text"])    # "send 40-100 photos"
        self.assertEqual(button_ids(first[0]), ["photos_done"])
        self.assertEqual(conversation.cover_photo(state), 1)
        for _ in range(59):
            self.assertEqual(talk(state, "photo"), [])  # quiet, no reply per photo
        self.assertEqual(state["photos"], 60)

        replies = talk(state, "button", "photos_done")
        self.assertIn("60", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["cover_yes", "cover_no", "add_photos"])

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
        self.assertEqual(state["step"], "cover_photo")   # still waiting for the cover photo

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
        talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", title_button)
        return state

    def test_done_too_early_then_add_photos(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")                      # the cover photo
        talk(state, "photo")
        talk(state, "button", "photos_done")      # tapped too early
        self.assertEqual(state["step"], "cover")
        replies = talk(state, "button", "add_photos")
        self.assertEqual(state["step"], "photos")
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        for _ in range(5):
            talk(state, "photo")
        replies = talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "cover")  # the title question comes again
        self.assertIn("7", replies[0]["text"])

    def test_add_photos_from_the_title_step(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_yes")
        talk(state, "button", "add_photos")
        self.assertEqual(state["step"], "photos")
        talk(state, "photo")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "cover")

    def test_add_photos_from_the_summary(self):
        state = self.finished_order()
        replies = talk(state, "button", "add_photos")
        self.assertEqual(state["step"], "photos")
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        talk(state, "photo")
        talk(state, "photo")
        replies = talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "done")   # straight to a new summary
        self.assertEqual(state["photos"], 4)
        self.assertIn("4", replies[0]["text"])

    def test_typing_change_something_shows_the_list(self):
        state = self.finished_order()
        replies = talk(state, "text", TEXTS["button_edit"])
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos"])

    def test_change_list_fits_whatsapp(self):
        # WhatsApp: the list's button up to 20 characters, each choice up to 24.
        self.assertLessEqual(len(TEXTS["button_edit"]), 20)
        self.assertLessEqual(len(TEXTS["edit_list_title"]), 24)
        for key in ["button_edit_title", "button_edit_design", "button_edit_cover",
                    "button_add_photos"]:
            self.assertLessEqual(len(TEXTS[key]), 24, key)
        self.assertLessEqual(len(TEXTS["button_add_photos"]), 20)  # also a button

    def test_reading_a_list_choice(self):
        message = {"type": "interactive",
                   "interactive": {"type": "list_reply", "list_reply": {"id": "add_photos"}}}
        self.assertEqual(conversation.read_message(message), ("button", "add_photos"))

    def test_summary_has_change_buttons(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        replies = talk(state, "button", "cover_no")
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos"])

    def test_change_the_cover_photo(self):
        state = self.finished_order()
        count = state["photos"]
        replies = talk(state, "button", "edit_cover")
        self.assertEqual(state["step"], "cover_photo")
        self.assertEqual(button_ids(replies[0]), ["keep_cover"])
        replies = talk(state, "photo")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["photos"], count + 1)              # also goes inside
        self.assertEqual(conversation.cover_photo(state), count + 1)
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos"])

    def test_keep_the_cover_photo(self):
        state = self.finished_order()
        talk(state, "button", "edit_cover")
        replies = talk(state, "text", "מה?")
        self.assertEqual(button_ids(replies[0]), ["keep_cover"])
        talk(state, "button", "keep_cover")
        self.assertEqual(state["step"], "done")
        self.assertEqual(conversation.cover_photo(state), 1)
        self.assertNotIn("editing", state["notes"])

    def test_photos_before_design_first_one_is_the_cover(self):
        state = conversation.new_state()
        talk(state, "photo")
        talk(state, "photo")
        talk(state, "button", "design_classic")
        self.assertEqual(state["step"], "photos")
        self.assertEqual(conversation.cover_photo(state), 1)

    def test_add_a_title_after_choosing_none(self):
        state = self.finished_order()
        replies = talk(state, "button", "edit_title")
        self.assertEqual(state["step"], "title")
        self.assertEqual(button_ids(replies[0]), ["cover_no", "add_photos"])
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
        self.assertEqual(state["photos"], 2)  # photos are kept
        self.assertIn("צבעוני", replies[0]["text"])

    def test_text_after_done_offers_the_change_buttons(self):
        state = self.finished_order()
        replies = talk(state, "text", "תודה")
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos"])

    def test_button_titles_fit_whatsapp(self):
        # WhatsApp refuses button titles longer than 20 characters.
        for key in ["design_classic", "design_colorful", "button_photos_done",
                    "button_cover_yes", "button_cover_no",
                    "button_edit_title", "button_edit_design",
                    "button_edit_cover", "button_keep_cover"]:
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


class FewPhotosTest(unittest.TestCase):
    """Tapping "done" too early: only the cover photo, or only a few photos."""

    def setUp(self):
        conversation.FEW_PHOTOS = 40   # the real value (the module's checks use 2)

    def tearDown(self):
        conversation.FEW_PHOTOS = 2

    def start(self, photos):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(photos):
            talk(state, "photo")
        return state

    def test_only_the_cover_photo_is_not_enough(self):
        state = self.start(1)
        replies = talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "photos")
        self.assertIn("תמונת הכריכה", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])

    def test_few_photos_asks_once_then_add_more(self):
        state = self.start(12)
        replies = talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "photos")
        self.assertIn("12 תמונות", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["add_photos", "few_photos_ok"])
        replies = talk(state, "button", "add_photos")
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        for _ in range(30):
            talk(state, "photo")
        replies = talk(state, "button", "photos_done")   # 42 photos: no question
        self.assertEqual(state["step"], "cover")

    def test_few_photos_continue_anyway(self):
        state = self.start(12)
        talk(state, "button", "photos_done")
        replies = talk(state, "button", "few_photos_ok")
        self.assertEqual(state["step"], "cover")
        self.assertIn("קיבלנו 12 תמונות", replies[0]["text"])
        talk(state, "button", "add_photos")                # back again from the title question
        talk(state, "photo")
        talk(state, "button", "photos_done")               # already said "continue": not asked again
        self.assertEqual(state["step"], "cover")

    def test_one_photo_in_correct_hebrew(self):
        self.assertEqual(conversation._photos(TEXTS, 1), "תמונה אחת")
        self.assertEqual(conversation._photos(TEXTS, 5), "5 תמונות")

    def test_buttons_fit_whatsapp(self):
        self.assertLessEqual(len(TEXTS["button_few_photos_ok"]), 20)


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
