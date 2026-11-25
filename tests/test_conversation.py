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


GOOD_COVER = {"ok": True, "problem": None, "dpi": 300, "without_hd": False}


def talk(state, kind, value=None, cover=GOOD_COVER):
    """One message from the customer. A cover photo is then checked at once
    (in the bot this happens in the background, task 2.5), with this result;
    cover=None leaves it waiting at the "checking…" step."""
    replies = conversation.answer(state, kind, value, TEXTS)
    number = conversation.checking_cover(state)
    if cover and number:
        replies = replies + conversation.cover_checked(state, number, cover, TEXTS)
    return replies


def button_ids(message):
    """The IDs of a message's buttons, or of its list's choices. The "🔄 להתחיל מחדש"
    button is left out here (RestartTest checks where it appears)."""
    rows = message["list"]["rows"] if "list" in message else message.get("buttons", [])
    return [row["id"] for row in rows if row["id"] != "restart"]


def has_restart(message):
    return any(b["id"] == "restart" for b in message.get("buttons", []))


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
        # Two messages (task 1.2b): HD + the clip first, the cover request last.
        self.assertEqual(len(replies), 2)
        self.assertIn("HD", replies[0]["text"])
        self.assertNotIn("כריכה", replies[0]["text"])
        self.assertIn("כריכה", replies[1]["text"])
        self.assertNotIn("video_file", replies[1])

        first = talk(state, "photo")             # the cover photo
        self.assertIn("בודקים", first[0]["text"])  # "got it, checking…" (task 2.5)
        self.assertIn("40", first[1]["text"])    # checked: "send 40-100 photos"
        self.assertEqual(button_ids(first[1]), [])  # no "done" above the photos to come
        self.assertTrue(has_restart(first[1]))
        self.assertEqual(conversation.cover_photo(state), 1)
        for _ in range(59):
            self.assertEqual(talk(state, "photo"), [])  # quiet, no reply per photo
        self.assertEqual(state["photos"], 60)
        settled = conversation.photos_settled(state, TEXTS)   # photos stopped arriving
        self.assertIn("קיבלנו 60 תמונות", settled[0]["text"])
        self.assertEqual(button_ids(settled[0]), ["photos_done"])   # "done" below the photos

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
        talk(state, "button", "restart_yes")   # "are you sure?" -> yes
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
        self.assertEqual(button_ids(replies[0]), ["photos_done", "no_change"])
        talk(state, "photo")
        talk(state, "photo")
        replies = talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "done")   # straight to a new summary
        self.assertEqual(state["photos"], 4)
        self.assertIn("4", replies[0]["text"])

    def test_typing_change_something_shows_the_list(self):
        state = self.finished_order()
        replies = talk(state, "text", TEXTS["button_edit"])
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos", "no_change"])

    def test_change_list_fits_whatsapp(self):
        # WhatsApp: the list's button up to 20 characters, each choice up to 24.
        self.assertLessEqual(len(TEXTS["button_edit"]), 20)
        self.assertLessEqual(len(TEXTS["edit_list_title"]), 24)
        for key in ["button_edit_title", "button_edit_design", "button_edit_cover",
                    "button_add_photos", "button_no_change"]:
            self.assertLessEqual(len(TEXTS[key]), 24, key)
        self.assertLessEqual(len(TEXTS["button_add_photos"]), 20)  # also a button

    def test_reading_a_list_choice(self):
        message = {"type": "interactive",
                   "interactive": {"type": "list_reply", "list_reply": {"id": "add_photos"}}}
        self.assertEqual(conversation.read_message(message), ("button", "add_photos"))

    def test_summary_has_no_buttons(self):
        # Task 1.2b (owner's test): "הכל נכון?" looked like a gate, but the album is
        # built at once. Changes are made after the link.
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")
        talk(state, "photo")
        talk(state, "button", "photos_done")
        replies = talk(state, "button", "cover_no")
        self.assertNotIn("buttons", replies[0])
        self.assertIn("קישור", replies[0]["text"])
        replies = talk(state, "button", "edit_menu")             # an old message's button
        self.assertEqual(button_ids(replies[0]), ["edit_title", "edit_design", "edit_cover", "add_photos", "no_change"])
        self.assertEqual(state["step"], "done")

    def test_all_correct_on_an_old_summary(self):
        state = self.finished_order()
        replies = talk(state, "button", "confirm")
        self.assertEqual(state["step"], "done")
        self.assertIn("לאישור", replies[0]["text"])
        self.assertNotIn("כתבו לנו", replies[0]["text"])          # no promise the bot can't keep yet
        self.assertEqual(talk(state, "button", "confirm"), [])   # a second tap: quiet

    def test_change_the_cover_photo(self):
        state = self.finished_order()
        count = state["photos"]
        replies = talk(state, "button", "edit_cover")
        self.assertEqual(state["step"], "cover_photo")
        self.assertEqual(button_ids(replies[0]), ["no_change"])
        replies = talk(state, "photo")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["photos"], count + 1)              # also goes inside
        self.assertEqual(conversation.cover_photo(state), count + 1)
        self.assertIn("קיבלנו הכול", replies[-1]["text"])         # the new summary

    def test_keep_the_cover_photo(self):
        state = self.finished_order()
        talk(state, "button", "edit_cover")
        replies = talk(state, "text", "מה?")
        self.assertEqual(button_ids(replies[0]), ["no_change"])
        talk(state, "button", "keep_cover")                       # an old message's button
        self.assertEqual(state["step"], "done")
        self.assertEqual(conversation.cover_photo(state), 1)
        self.assertNotIn("editing", state["notes"])

    def start_cover(self):
        """A new customer who just sent their cover photo; the check isn't done yet."""
        state = conversation.new_state()
        talk(state, "text", "היי")
        talk(state, "button", "design_classic")
        replies = talk(state, "photo", cover=None)
        self.assertEqual(state["step"], "cover_check")
        self.assertIn("בודקים", replies[0]["text"])
        return state

    def test_cover_check_good(self):
        state = self.start_cover()
        self.assertIsNone(conversation.cover_photo(state))       # not yet accepted
        self.assertIn("עוד רגע", talk(state, "text", "נו?", cover=None)[0]["text"])
        self.assertEqual(talk(state, "photo", cover=None), [])   # the rest, counted quietly
        self.assertEqual(state["photos"], 2)
        replies = conversation.cover_checked(state, 1, GOOD_COVER, TEXTS)
        self.assertEqual(state["step"], "photos")
        self.assertEqual(conversation.cover_photo(state), 1)
        self.assertIn("יפה", replies[0]["text"])
        self.assertEqual(conversation.cover_checked(state, 1, GOOD_COVER, TEXTS), [])  # only once

    def test_cover_check_failed_accepts_the_photo(self):
        state = self.start_cover()
        conversation.cover_checked(state, 1, None, TEXTS)       # e.g. album tools missing
        self.assertEqual((state["step"], conversation.cover_photo(state)), ("photos", 1))

    def test_small_cover_without_hd_send_again(self):
        state = self.start_cover()
        small = {"ok": False, "problem": "small", "dpi": 146, "without_hd": True}
        replies = conversation.cover_checked(state, 1, small, TEXTS)
        self.assertEqual(state["step"], "cover_problem")
        self.assertIn("HD", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["cover_new", "cover_keep"])
        self.assertEqual(replies[0]["buttons"][0]["title"], TEXTS["button_cover_new_hd"])
        self.assertEqual(button_ids(talk(state, "text", "מה?")[0]), ["cover_new", "cover_keep"])
        talk(state, "button", "cover_new")
        self.assertEqual(state["step"], "cover_photo")
        replies = talk(state, "photo")                           # sent again in HD: good
        self.assertEqual((state["step"], state["photos"]), ("photos", 2))
        self.assertEqual(conversation.cover_photo(state), 2)     # the first stays inside
        self.assertNotIn("cover_kept", state["notes"])

    def test_blurry_cover_photo_instead_of_tapping(self):
        state = self.start_cover()
        blurry = {"ok": False, "problem": "blurry", "dpi": 300, "without_hd": False}
        replies = conversation.cover_checked(state, 1, blurry, TEXTS)
        self.assertIn("מטושטשת", replies[0]["text"])
        self.assertNotIn("HD", replies[0]["text"])
        talk(state, "photo", cover=None)                         # a new photo = the new cover
        self.assertEqual(conversation.checking_cover(state), 2)

    def test_low_cover_without_hd_kept_full_size(self):
        state = self.start_cover()
        low = {"ok": False, "problem": "low", "dpi": 195, "without_hd": True}
        replies = conversation.cover_checked(state, 1, low, TEXTS)
        self.assertIn("HD", replies[0]["text"])
        self.assertEqual(replies[0]["buttons"][0]["title"], TEXTS["button_cover_new_hd"])
        replies = talk(state, "button", "cover_keep")
        self.assertEqual(conversation.cover_photo(state), 1)
        self.assertEqual(replies[0]["text"], TEXTS["cover_kept_full"].format(max=conversation.MAX_PHOTOS))
        self.assertNotIn("קטנה", replies[0]["text"])       # not made smaller

    def test_cover_too_wide(self):
        state = self.start_cover()
        shape = {"ok": False, "problem": "shape", "dpi": 385, "without_hd": False}
        replies = conversation.cover_checked(state, 1, shape, TEXTS)
        self.assertEqual(replies[0]["text"], TEXTS["cover_problem_shape"])
        self.assertEqual(replies[0]["buttons"][0]["title"], TEXTS["button_cover_new"])
        replies = talk(state, "button", "cover_keep")
        self.assertIn("קטנה", replies[0]["text"])          # "we'll show it smaller"

    def test_keep_a_small_cover(self):
        state = self.start_cover()
        small = {"ok": False, "problem": "small", "dpi": 120, "without_hd": False}
        conversation.cover_checked(state, 1, small, TEXTS)
        replies = talk(state, "button", "cover_keep")
        self.assertEqual((state["step"], conversation.cover_photo(state)), ("photos", 1))
        self.assertIn("cover_kept", state["notes"])
        self.assertIn("קטנה", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), [])   # "done" comes after the photos

    def test_small_new_cover_from_the_summary(self):
        state = self.finished_order()
        talk(state, "button", "edit_cover")
        talk(state, "photo", cover=None)
        small = {"ok": False, "problem": "small", "dpi": 120, "without_hd": False}
        conversation.cover_checked(state, state["photos"], small, TEXTS)
        self.assertEqual(conversation.cover_photo(state), 1)     # the old cover, until decided
        talk(state, "button", "cover_new")
        replies = talk(state, "button", "no_change")             # "keep as it was"
        self.assertEqual((state["step"], conversation.cover_photo(state)), ("done", 1))
        self.assertIn("קיבלנו הכול", replies[0]["text"])          # the summary (album rebuilt:
        #                                                           the new photo goes inside)
        # And keeping the small one goes straight back to the summary.
        talk(state, "button", "edit_cover")
        talk(state, "photo", cover=None)
        conversation.cover_checked(state, state["photos"], small, TEXTS)
        replies = talk(state, "button", "cover_keep")
        self.assertEqual(state["step"], "done")
        self.assertEqual(conversation.cover_photo(state), state["photos"])
        self.assertIn("cover_kept", state["notes"])

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
        self.assertEqual(button_ids(replies[0]), ["cover_no", "no_change"])
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
        self.assertEqual(button_ids(replies[0]), ["design_classic", "design_colorful", "no_change"])
        replies = talk(state, "button", "design_colorful")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["design"], "colorful")
        self.assertEqual(state["photos"], 2)  # photos are kept
        self.assertIn("צבעוני", replies[0]["text"])

    def test_text_before_the_link_says_changes_come_there(self):
        state = self.finished_order()
        replies = talk(state, "text", "תודה")
        self.assertNotIn("buttons", replies[0])
        self.assertIn("קישור", replies[0]["text"])
        self.assertEqual(talk(state, "text", "תודה"), [])        # said once

    def test_emojis_are_removed_from_the_title(self):
        # The album's font can't print emojis: they showed as an empty box on the cover.
        state = self.finished_order(title_button="cover_yes")
        talk(state, "text", "📖 אלבום ניסוי 4 ❤️👨‍👩‍👧")
        self.assertEqual(state["title"], "אלבום ניסוי 4")
        self.assertEqual(conversation.printable("חופשה בְּאילת, 2026 ₪!"), "חופשה בְּאילת, 2026 ₪!")

    def test_a_title_of_only_emojis_asks_again(self):
        state = self.finished_order(title_button="cover_yes")
        replies = talk(state, "text", "😍😍")
        self.assertEqual(state["step"], "title")
        self.assertIsNone(state["title"])
        self.assertEqual(button_ids(replies[0]), ["cover_no"])

    def test_after_previews(self):
        # album_job.py sent the previews and added this note (task 2.4).
        state = self.finished_order()
        state["notes"].append("previews_sent")
        replies = talk(state, "text", "וואו")
        self.assertEqual(button_ids(replies[0]), ["preview_ok", "edit_menu"])
        self.assertEqual(talk(state, "text", "וואו"), [])   # only once
        replies = talk(state, "button", "preview_ok")
        self.assertIn("בדיקה אחרונה", replies[0]["text"])
        self.assertTrue(state.pop("ask_owner"))   # orders.py asks the owner (task 3.1)
        self.assertEqual(talk(state, "button", "preview_ok"), [])
        self.assertNotIn("ask_owner", state)       # only once

    def test_after_love_it_typed_text_goes_to_the_owner(self):
        state = self.finished_order()
        state["notes"] += ["previews_sent", "preview_ok", "owner_check", "owner_token:abc"]
        replies = talk(state, "text", "  מתי זה יגיע? ")
        self.assertEqual(state.pop("for_owner"), "מתי זה יגיע?")
        self.assertIn("לצוות", replies[0]["text"])

    def test_a_change_needs_a_new_approval(self):
        state = self.finished_order()
        state["notes"] += ["previews_sent", "preview_ok", "owner_check",
                           "owner_token:abc", "approved"]
        talk(state, "button", "edit_title")
        talk(state, "text", "כותרת חדשה")
        for note in ("preview_ok", "owner_check", "owner_token:abc", "approved"):
            self.assertNotIn(note, state["notes"])

    def test_a_change_after_previews_sends_new_previews(self):
        state = self.finished_order()
        state["notes"] += ["previews_sent", "preview_ok"]
        talk(state, "button", "edit_title")
        talk(state, "text", "כותרת חדשה")
        self.assertEqual(state["step"], "done")
        for note in ("previews_sent", "preview_ok"):
            self.assertNotIn(note, state["notes"])

    def test_button_titles_fit_whatsapp(self):
        # WhatsApp refuses button titles longer than 20 characters.
        for key in ["button_confirm", "design_classic", "design_colorful", "button_photos_done",
                    "button_cover_yes", "button_cover_no",
                    "button_edit_title", "button_edit_design",
                    "button_edit_cover", "button_keep_cover", "button_preview_ok",
                    "button_preview_link", "button_cover_new", "button_cover_new_hd",
                    "button_cover_keep", "button_owner_ok", "button_owner_problem",
                    "button_owner_write"]:
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


class RestartTest(unittest.TestCase):
    """The "🔄 להתחיל מחדש" button and the "are you sure?" question."""

    def setUp(self):
        conversation.FEW_PHOTOS = 40   # the real value, so "only a few photos?" is asked

    def tearDown(self):
        conversation.FEW_PHOTOS = 2

    def at_photos(self, photos=3):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(photos):
            talk(state, "photo")
        return state

    def finished(self):
        state = self.at_photos(5)
        talk(state, "button", "photos_done")
        talk(state, "button", "few_photos_ok")
        talk(state, "button", "cover_no")
        self.assertEqual(state["step"], "done")
        return state

    def test_not_on_the_first_design_question(self):
        state = conversation.new_state()
        replies = talk(state, "text", "שלום")
        self.assertFalse(has_restart(replies[1]))

    def test_on_messages_with_room_for_it(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        replies = talk(state, "photo")                             # the cover: checking…, then OK
        self.assertFalse(has_restart(replies[0]))                  # plain text: left alone
        self.assertTrue(has_restart(replies[-1]))                  # "done" button + restart
        talk(state, "photo")
        few = talk(state, "button", "photos_done")[0]              # add photos / continue
        self.assertTrue(has_restart(few))
        self.assertEqual(len(few["buttons"]), 3)
        cover = talk(state, "button", "few_photos_ok")[0]          # already 3 buttons
        self.assertFalse(has_restart(cover))
        title = talk(state, "button", "cover_yes")[0]
        self.assertTrue(has_restart(title))
        summary = talk(state, "text", "הטיול")[0]
        self.assertFalse(has_restart(summary))                     # it's in the list
        listed = talk(state, "button", "edit_menu")[0]
        self.assertIn("restart", [row["id"] for row in listed["list"]["rows"]])

    def test_asks_first_then_no_keeps_everything(self):
        state = self.at_photos()
        replies = talk(state, "button", "restart")
        self.assertEqual(button_ids(replies[0]), ["restart_yes", "restart_no"])
        self.assertIn("3 תמונות", replies[0]["text"])
        replies = talk(state, "button", "restart_no")
        self.assertEqual(state["step"], "photos")
        self.assertEqual(state["photos"], 3)
        self.assertEqual(button_ids(replies[1]), ["photos_done"])

    def test_yes_starts_over(self):
        state = self.at_photos()
        talk(state, "button", "restart")
        replies = talk(state, "button", "restart_yes")
        self.assertEqual(state["step"], "design")
        self.assertEqual(state["photos"], 0)
        self.assertEqual(button_ids(replies[1]), ["design_classic", "design_colorful"])

    def test_typing_new_album_also_asks(self):
        state = self.at_photos()
        replies = talk(state, "text", "אלבום חדש")
        self.assertEqual(button_ids(replies[0]), ["restart_yes", "restart_no"])
        self.assertEqual(state["photos"], 3)

    def test_nothing_to_lose_starts_over_at_once(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        replies = talk(state, "text", "אלבום חדש")
        self.assertEqual(state["step"], "design")
        self.assertIn("ברוכים הבאים", replies[0]["text"])

    def test_an_old_yes_button_asks_again(self):
        state = self.at_photos()
        talk(state, "button", "restart")
        talk(state, "photo")                          # they carried on instead
        replies = talk(state, "button", "restart_yes")
        self.assertEqual(state["photos"], 4)          # nothing deleted
        self.assertEqual(button_ids(replies[0]), ["restart_yes", "restart_no"])

    def test_after_the_summary_the_album_is_kept(self):
        state = self.finished()
        replies = talk(state, "button", "restart")
        self.assertIn("נשמר", replies[0]["text"])
        talk(state, "button", "restart_no")
        self.assertEqual(state["step"], "done")

    def test_buttons_fit_whatsapp(self):
        for key in ["button_restart", "button_restart_yes", "button_restart_no"]:
            self.assertLessEqual(len(TEXTS[key]), 20, key)
        self.assertLessEqual(len(TEXTS["button_restart_list"]), 24)


class ArrivingPhotosTest(unittest.TestCase):
    """The WhatsApp "album" bundle, videos, and photos still arriving."""

    def at_photos(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(3):
            talk(state, "photo")
        return state

    def test_the_album_bundle_gets_no_answer(self):
        state = self.at_photos()
        self.assertEqual(talk(state, "other", "unsupported"), [])
        talk(state, "photo")
        self.assertEqual(state["photos"], 4)

    def test_a_video_gets_a_clear_message_once(self):
        state = self.at_photos()
        replies = talk(state, "other", "video")
        self.assertIn("סרטונים לא נכנסים", replies[0]["text"])
        self.assertEqual(talk(state, "other", "video"), [])

    def test_done_while_photos_arrive_waits(self):
        state = self.at_photos()
        state["recent_photo"] = True
        replies = talk(state, "button", "photos_done")
        self.assertIn("מוודאים", replies[0]["text"])
        self.assertEqual(state["step"], "photos")
        del state["recent_photo"]
        talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertEqual(state["step"], "cover")
        self.assertIn("4 תמונות", replies[0]["text"])
        self.assertEqual(conversation.photos_settled(state, TEXTS), [])   # only once

    def test_photo_after_the_summary_is_added(self):
        state = self.at_photos()
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        self.assertEqual(state["step"], "done")
        replies = talk(state, "photo")
        self.assertEqual(state["photos"], 4)
        self.assertTrue(state.pop("rebuild"))
        self.assertIn("נוסיף", replies[0]["text"])
        self.assertEqual(talk(state, "photo"), [])
        self.assertEqual(state["photos"], 5)


class DoneButtonBelowPhotosTest(unittest.TestCase):
    """The "done" button comes after the photos (owner's test, Nov 24, 2026)."""

    def after_cover(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        talk(state, "photo")                              # the cover
        return state

    def test_count_with_done_button_once_photos_stop(self):
        state = self.after_cover()
        self.assertEqual(conversation.photos_settled(state, TEXTS), [])   # only the cover: nothing to say
        for _ in range(20):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertIn("קיבלנו 21 תמונות", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        self.assertTrue(has_restart(replies[0]))
        self.assertEqual(conversation.photos_settled(state, TEXTS), [])   # same count: quiet
        for _ in range(5):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertIn("קיבלנו 26 תמונות", replies[0]["text"])          # updated count

    def test_few_photos_said_in_the_count_not_asked_again(self):
        conversation.FEW_PHOTOS = 40
        try:
            state = self.after_cover()
            for _ in range(11):
                talk(state, "photo")
            replies = conversation.photos_settled(state, TEXTS)
            self.assertIn("לפחות 40", replies[0]["text"])
            replies = talk(state, "button", "photos_done")
            self.assertEqual(state["step"], "cover")        # no second "only 12?" question
            talk(state, "button", "add_photos")
            talk(state, "photo")
            replies = talk(state, "button", "photos_done")   # 13 photos, not told yet: asked
            self.assertEqual(button_ids(replies[0]), ["add_photos", "few_photos_ok"])
        finally:
            conversation.FEW_PHOTOS = 2

    def test_video_with_the_photos_is_said_in_the_count(self):
        """Task 1.2b: one message (count + videos), not a video message, then silence."""
        state = self.after_cover()
        talk(state, "photo")
        state["recent_photo"] = True                      # photos are still arriving
        self.assertEqual(talk(state, "other", "video"), [])
        self.assertEqual(talk(state, "other", "video"), [])
        del state["recent_photo"]
        talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        lines = replies[0]["text"].split("\n")
        self.assertIn("קיבלנו 3 תמונות", lines[0])
        self.assertIn("סרטונים לא נכנסים", lines[1])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertNotIn("סרטונים", replies[0]["text"])   # said once

    def test_video_mid_photos_has_no_done_button(self):
        state = self.after_cover()
        replies = talk(state, "other", "video")
        self.assertNotIn("buttons", replies[0])

    def test_add_photos_from_the_summary_doesnt_repeat_the_count(self):
        state = self.after_cover()
        for _ in range(3):
            talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        talk(state, "button", "add_photos")              # "already got 4 photos" + done
        self.assertEqual(conversation.photos_settled(state, TEXTS), [])
        talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertIn("קיבלנו 5 תמונות", replies[0]["text"])


class HdVideoTest(unittest.TestCase):
    """The HD how-to clip and "continue without HD" (owner's test, Nov 24, 2026)."""

    def test_clip_is_in_the_project(self):
        self.assertTrue(conversation.HD_VIDEO.exists())

    def test_clip_on_the_hd_instructions(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        replies = talk(state, "button", "design_classic")
        self.assertEqual(replies[0].get("video_file"), str(conversation.HD_VIDEO))
        problem = conversation.cover_problem_message(TEXTS, "small_hd")
        self.assertIn("video_file", problem)
        self.assertNotIn("video_file", conversation.cover_problem_message(TEXTS, "blurry"))

    def test_how_to_can_still_continue_without_hd(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(6):
            talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        state["step"] = "hd_question"                     # what album_job.py does
        replies = talk(state, "button", "hd_help")       # a short warning, no clip
        self.assertNotIn("video_file", replies[0])
        self.assertEqual(button_ids(replies[0]), ["hd_how", "hd_continue"])
        replies = talk(state, "button", "hd_how")        # "how?": the clip and the steps
        self.assertIn("video_file", replies[0])
        self.assertEqual(button_ids(replies[0]), ["hd_continue"])
        self.assertEqual(state["photos"], 6)              # nothing deleted
        talk(state, "button", "hd_continue")              # changed their mind
        self.assertEqual((state["step"], state["photos"]), ("done", 6))

    def test_typed_continue_without_hd(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(3):
            talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        state["step"] = "hd_question"
        talk(state, "text", "להמשיך בלי HD")
        self.assertEqual(state["step"], "done")

    def test_hd_button_titles_fit_whatsapp(self):
        self.assertLessEqual(len(TEXTS["button_hd_continue_no_hd"]), 20)


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
        self.assertEqual(button_ids(replies[0]), [])   # "done" comes after the photos

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
        self.assertEqual(button_ids(replies[0]), ["hd_how", "hd_continue"])
        self.assertEqual((state["step"], state["photos"]), ("hd_question", 5))   # nothing deleted yet
        self.assertNotIn("resend_photos", state)
        talk(state, "photo")                          # the first new photo replaces the old ones
        self.assertEqual((state["step"], state["photos"]), ("photos", 1))
        self.assertTrue(state.pop("resend_photos"))
        for _ in range(3):
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
        self.assertEqual(button_ids(replies[0]), [])   # "done" comes after the photos

    def test_other_text_repeats_the_question(self):
        state = self.finished_state()
        state["step"] = "hd_question"
        replies = talk(state, "text", "מה?")
        self.assertEqual(button_ids(replies[0]), ["hd_help", "hd_continue"])


class PhotoChangeTest(unittest.TestCase):
    """Task 3.2: replace or remove a photo by the number shown in the preview."""

    def finished(self, photos=6):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(photos):
            talk(state, "photo")
        talk(state, "button", "photos_done")
        talk(state, "button", "cover_no")
        state["notes"].append("previews_sent")   # album_job.py sent the previews
        return state

    def test_the_list_offers_it_only_after_the_previews(self):
        state = self.finished()
        replies = talk(state, "button", "edit_menu")
        self.assertEqual(button_ids(replies[0])[0], "edit_photo")
        state["notes"].remove("previews_sent")
        replies = talk(state, "button", "edit_menu")
        self.assertNotIn("edit_photo", button_ids(replies[0]))

    def test_remove_a_photo(self):
        state = self.finished()
        replies = talk(state, "button", "edit_photo")
        self.assertEqual(state["step"], "photo_number")
        self.assertIn("מספר", replies[0]["text"])
        replies = talk(state, "text", "תמונה 4")
        self.assertEqual(state["step"], "photo_action")
        self.assertEqual(button_ids(replies[0]), ["photo_replace", "photo_remove", "no_change"])
        replies = talk(state, "button", "photo_remove")
        self.assertIn("4", replies[0]["text"])
        self.assertIn("removed:4", state["notes"])
        self.assertEqual(state["step"], "done")
        self.assertNotIn("previews_sent", state["notes"])   # built and sent again
        self.assertIn("תמונות: 5", replies[1]["text"])       # the summary counts 6 - 1

    def test_replace_a_photo(self):
        state = self.finished()
        talk(state, "button", "edit_photo")
        talk(state, "text", "3")
        replies = talk(state, "button", "photo_replace")
        self.assertEqual(state["step"], "photo_replace")
        self.assertIn("3", replies[0]["text"])
        replies = talk(state, "photo")
        self.assertEqual(state["photos"], 7)                 # saved as photo 7
        self.assertIn("replaced:3:7", state["notes"])
        self.assertEqual(state["step"], "done")
        self.assertIn("תמונות: 6", replies[-1]["text"])

    def test_only_numbers_in_the_album(self):
        state = self.finished()
        talk(state, "button", "edit_photo")
        state["album_numbers"] = {2, 3, 5}      # what orders.py reads from the album
        replies = talk(state, "text", "4")
        self.assertIn("לא מצאנו", replies[0]["text"])
        self.assertEqual(state["step"], "photo_number")
        replies = talk(state, "text", "שלום")
        self.assertIn("רק את המספר", replies[0]["text"])
        talk(state, "text", "5")
        self.assertEqual(state["step"], "photo_action")

    def test_without_the_album_the_cover_and_changed_photos_are_not_offered(self):
        state = self.finished()
        state["notes"].append("removed:2")
        talk(state, "button", "edit_photo")
        for number in ("1", "2", "99"):        # 1 is the cover photo
            talk(state, "text", number)
            self.assertEqual(state["step"], "photo_number")

    def test_keep_as_it_was(self):
        state = self.finished()
        talk(state, "button", "edit_photo")
        talk(state, "text", "3")
        replies = talk(state, "button", "no_change")
        self.assertEqual(state["step"], "done")
        self.assertIn("previews_sent", state["notes"])   # nothing changed: no new build
        self.assertTrue(state.pop("unchanged"))
        self.assertNotIn("editing", state["notes"])
        self.assertIsNone(conversation._note(state, "photo_pick"))
        self.assertEqual(button_ids(replies[0]), ["preview_ok", "edit_menu"])

    def test_a_photo_while_choosing_the_number_is_not_counted(self):
        state = self.finished()
        talk(state, "button", "edit_photo")
        talk(state, "photo")
        self.assertEqual(state["photos"], 6)

    def test_the_number_of_changes_is_limited(self):
        state = self.finished()
        state["notes"] += [f"removed:{n}" for n in range(conversation.MAX_PHOTO_CHANGES)]
        replies = talk(state, "button", "edit_photo")
        self.assertEqual(state["step"], "done")
        self.assertIn(str(conversation.MAX_PHOTO_CHANGES), replies[0]["text"])
        talk(state, "text", "בבקשה גם להסיר את 20")
        self.assertEqual(state.pop("for_owner"), "בבקשה גם להסיר את 20")

    def test_resending_in_hd_forgets_the_changes(self):
        state = self.finished()
        state["notes"] += ["removed:2", "replaced:3:7"]
        state["step"] = "hd_question"
        talk(state, "photo")
        self.assertEqual(conversation.photo_changes(state), [])


class AddressPaymentTest(unittest.TestCase):
    """Task 3.2: after the owner approves: the address, then the payment."""

    def approved(self):
        state = PhotoChangeTest.finished(None)
        state["notes"] += ["preview_ok", "approved"]
        conversation.owner_approved(state)    # orders.py, when the owner approves
        return state

    def test_address_then_payment(self):
        state = self.approved()
        self.assertEqual(state["step"], "address")
        replies = talk(state, "text", "דנה כהן\nהרצל 5\n  תל אביב\n050-1112222")
        self.assertEqual(state["address"], "דנה כהן\nהרצל 5\nתל אביב\n050-1112222")
        self.assertEqual(state["step"], "address_check")
        self.assertIn("הרצל 5", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["address_ok", "address_fix"])
        self.assertFalse(has_restart(replies[0]))
        replies = talk(state, "button", "address_ok")
        self.assertEqual(state["step"], "payment")
        self.assertTrue(state.pop("ask_payment"))     # orders.py tells the owner
        price, shipping, total = conversation.payment_amounts()
        self.assertEqual(state["price"], total)
        self.assertIn(f"₪{total}", replies[0]["text"])
        self.assertIn("ביט", replies[0]["text"])
        self.assertIn("payment_wait", state["notes"])
        replies = talk(state, "text", "שילמתי")
        self.assertEqual(state.pop("for_owner"), "שילמתי")
        conversation.owner_paid(state)
        self.assertEqual(state["step"], "paid")
        self.assertNotIn("payment_wait", state["notes"])

    def test_a_short_address_asks_again(self):
        state = self.approved()
        replies = talk(state, "text", "חיפה")
        self.assertEqual(state["step"], "address")
        self.assertIn("חסרים", replies[0]["text"])

    def test_fix_the_address(self):
        state = self.approved()
        talk(state, "text", "רחוב הגפן 1, חיפה")
        talk(state, "button", "address_fix")
        self.assertEqual(state["step"], "address")
        talk(state, "text", "רחוב הגפן 3, חיפה, 0501234567")
        self.assertIn("3", state["address"])
        # Typing a new address instead of tapping also works.
        talk(state, "text", "רחוב הזית 9, עכו, 0501234567")
        self.assertEqual(state["step"], "address_check")
        self.assertIn("הזית", state["address"])

    def test_the_album_cant_be_changed_after_approval(self):
        state = self.approved()
        replies = talk(state, "button", "edit_menu")
        self.assertIn("כבר אושר", replies[0]["text"])
        self.assertEqual(state["step"], "address")
        replies = talk(state, "text", "אפשר להחליף את תמונה 5?")
        self.assertEqual(state.pop("for_owner"), "אפשר להחליף את תמונה 5?")
        self.assertIsNone(state.get("address"))          # not taken as the address
        self.assertIn("לאן לשלוח", replies[-1]["text"])  # and asked again
        talk(state, "photo")
        self.assertEqual(state["photos"], 6)              # photos aren't added any more

    def test_starting_over_keeps_the_approved_album(self):
        state = self.approved()
        replies = talk(state, "text", "אלבום חדש")
        self.assertIn("נשמר", replies[0]["text"])


class HelpTest(unittest.TestCase):
    """Task 3.2 (decided in 1.2b): "עזרה" sends one typed question a day to the owner."""

    def setUp(self):
        self.state = conversation.new_state()
        talk(self.state, "text", "שלום")
        talk(self.state, "button", "design_classic")
        self._today = conversation._today
        conversation._today = lambda: "2026-11-25"

    def tearDown(self):
        conversation._today = self._today

    def test_help_passes_the_next_message_to_the_owner(self):
        replies = talk(self.state, "text", "עזרה")
        self.assertIn("כתבו כאן את השאלה", replies[0]["text"])
        talk(self.state, "photo")                       # a photo is never passed on
        self.assertNotIn("help_for_owner", self.state)
        replies = talk(self.state, "text", "איך שולחים כמה תמונות ביחד?")
        self.assertEqual(self.state.pop("help_for_owner"), "איך שולחים כמה תמונות ביחד?")
        self.assertIn("קיבלנו", replies[0]["text"])
        self.assertEqual(self.state["step"], "photos")   # nothing else changed

    def test_once_a_day(self):
        talk(self.state, "text", "עזרה")
        talk(self.state, "text", "שאלה")
        self.state.pop("help_for_owner")
        replies = talk(self.state, "text", "עזרה")
        self.assertIn("ההודעה הקודמת", replies[0]["text"])
        talk(self.state, "text", "עוד שאלה")
        self.assertNotIn("help_for_owner", self.state)
        conversation._today = lambda: "2026-11-26"      # the next day: allowed again
        talk(self.state, "text", "עזרה")
        talk(self.state, "text", "שאלה חדשה")
        self.assertEqual(self.state.pop("help_for_owner"), "שאלה חדשה")

    def test_long_questions_are_cut(self):
        talk(self.state, "text", "עזרה")
        talk(self.state, "text", "א" * 900)
        question = self.state.pop("help_for_owner")
        self.assertEqual(len(question), conversation.HELP_MAX_LETTERS + 1)

    def test_a_button_cancels_it(self):
        talk(self.state, "text", "עזרה")
        talk(self.state, "button", "no_change")
        talk(self.state, "text", "בלי כותרת")
        self.assertNotIn("help_for_owner", self.state)
        self.assertNotIn("help_wait", self.state["notes"])


if __name__ == "__main__":
    unittest.main()


class EarlyHdQuestionTest(unittest.TestCase):
    """Task 1.2b: "resend in HD?" comes with the photo count, before the title and
    the summary (owner's test: asked after the summary, it was confusing)."""

    def asked(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(6):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS, without_hd=True)
        return state, replies

    def test_asked_with_the_count(self):
        state, replies = self.asked()
        self.assertEqual(state["step"], "hd_question")
        self.assertIn("קיבלנו 6 תמונות", replies[0]["text"])
        self.assertIn("HD", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["hd_help", "hd_continue"])
        self.assertTrue(has_restart(replies[0]))
        self.assertEqual(conversation.photos_settled(state, TEXTS, without_hd=True), [])   # once

    def test_continue_goes_back_to_the_photos(self):
        state, _ = self.asked()
        replies = talk(state, "button", "hd_continue")
        self.assertEqual(state["step"], "photos")
        self.assertIn("6 תמונות", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        self.assertEqual(conversation.photos_settled(state, TEXTS, without_hd=True), [])   # not again
        talk(state, "button", "photos_done")
        self.assertEqual(state["step"], "cover")          # the normal way on: title, summary

    def test_yes_shows_how_and_new_photos_replace_the_old(self):
        state, _ = self.asked()
        replies = talk(state, "button", "hd_help")
        self.assertEqual(button_ids(replies[0]), ["hd_how", "hd_continue"])
        self.assertTrue(has_restart(replies[0]))          # 3 buttons, WhatsApp's limit
        self.assertEqual(state["photos"], 6)              # nothing deleted yet
        talk(state, "photo")
        self.assertTrue(state.pop("resend_photos"))
        self.assertEqual((state["step"], state["photos"]), ("photos", 1))
        self.assertNotIn("hd_early", state["notes"])
        for _ in range(4):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS, without_hd=True)   # asked only once
        self.assertIn("קיבלנו 5 תמונות", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])

    def test_done_tapped_while_arriving_asks_hd_first(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(4):
            talk(state, "photo")
        state["recent_photo"] = True
        talk(state, "button", "photos_done")
        del state["recent_photo"]
        replies = conversation.photos_settled(state, TEXTS, without_hd=True)
        self.assertEqual(state["step"], "hd_question")
        self.assertNotIn("done_waiting", state["notes"])
        self.assertEqual(button_ids(replies[0]), ["hd_help", "hd_continue"])

    def test_a_typed_word_repeats_the_early_question(self):
        state, _ = self.asked()
        replies = talk(state, "text", "מה?")
        self.assertIn("קיבלנו 6 תמונות", replies[0]["text"])

    def test_with_hd_the_count_as_usual(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(6):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS, without_hd=False)
        self.assertEqual(state["step"], "photos")
        self.assertEqual(button_ids(replies[0]), ["photos_done"])


class TextsTest(unittest.TestCase):
    """Task 1.2b: owner's feedback on the texts."""

    def test_every_button_fits_whatsapp(self):
        for key, value in TEXTS.items():
            if key.startswith("button_"):
                self.assertLessEqual(len(value), 20, key)

    def test_welcome_breaks_after_hello(self):
        self.assertTrue(TEXTS["welcome"].startswith("שלום! 👋\n"))

    def test_restart_button_says_start_over(self):
        self.assertIn("להתחיל מחדש", TEXTS["button_restart"])
        self.assertIn(conversation._clean(TEXTS["button_restart"].replace("🔄", "")),
                      [conversation._clean(w) for w in TEXTS["restart_words"]])


class NoChangeTest(unittest.TestCase):
    """Task 1.2b (owner's test): "✏️ לשנות משהו" tapped by mistake."""

    def after_previews(self):
        state = conversation.new_state()
        for kind, value in (("text", "שלום"), ("button", "design_classic"), ("photo", None),
                            ("photo", None), ("photo", None), ("button", "photos_done"),
                            ("button", "cover_no")):
            talk(state, kind, value)
        state["notes"].append("previews_sent")              # what album_job.py does
        return state

    def test_from_the_list(self):
        state = self.after_previews()
        talk(state, "button", "edit_menu")
        replies = talk(state, "button", "no_change")
        self.assertEqual(state["step"], "done")
        self.assertTrue(state.pop("unchanged"))             # the album is not built again
        self.assertIn("previews_sent", state["notes"])
        self.assertEqual(button_ids(replies[0]), ["preview_ok", "edit_menu"])
        self.assertIn("בלי שינויים", replies[0]["text"])

    def test_from_each_change_step(self):
        for choice in ("edit_title", "edit_design", "edit_cover", "add_photos"):
            state = self.after_previews()
            talk(state, "button", "edit_menu")
            replies = talk(state, "button", choice)
            self.assertIn("no_change", button_ids(replies[0]), choice)
            title, design = state["title"], state["design"]
            replies = talk(state, "button", "no_change")
            self.assertEqual(state["step"], "done", choice)
            self.assertTrue(state.pop("unchanged"), choice)
            self.assertEqual((state["title"], state["design"]), (title, design))
            self.assertFalse([n for n in state["notes"] if n == "editing" or n.startswith("photos_at")])
            self.assertEqual(button_ids(replies[0]), ["preview_ok", "edit_menu"], choice)

    def test_photos_sent_meanwhile_still_go_in(self):
        state = self.after_previews()
        talk(state, "button", "add_photos")
        talk(state, "photo")
        replies = talk(state, "button", "no_change")
        self.assertEqual((state["step"], state["photos"]), ("done", 4))
        self.assertNotIn("unchanged", state)                # built again with the new photo
        self.assertIn("קיבלנו הכול", replies[0]["text"])

    def test_typed_text_works_too(self):
        state = self.after_previews()
        talk(state, "button", "edit_title")
        talk(state, "text", TEXTS["button_no_change"])
        self.assertEqual(state["step"], "done")
        self.assertIsNone(state["title"])                   # not saved as the title


class HdResendTextsTest(unittest.TestCase):
    """Task 1.2b (owner's test): resending in HD deletes the old photos; say so clearly."""

    def test_warning_first_and_old_count_in_the_new_count(self):
        state = conversation.new_state()
        talk(state, "text", "שלום")
        talk(state, "button", "design_classic")
        for _ in range(53):
            talk(state, "photo")
        conversation.photos_settled(state, TEXTS, without_hd=True)
        replies = talk(state, "button", "hd_help")
        self.assertTrue(replies[0]["text"].startswith("⚠️"))
        self.assertIn("(53 תמונות) יימחקו", replies[0]["text"].split("\n\n")[0])
        replies = talk(state, "photo")
        self.assertIn("נמחקו", replies[0]["text"])
        for _ in range(9):
            talk(state, "photo")
        replies = conversation.photos_settled(state, TEXTS)
        self.assertIn("קיבלנו 10 תמונות ב-HD 👍 (במקום 53 הקודמות)", replies[0]["text"])
        self.assertEqual(button_ids(replies[0]), ["photos_done"])
        talk(state, "button", "photos_done")
        self.assertNotIn("resent_from:53", state["notes"])
