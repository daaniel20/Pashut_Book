"""The customer conversation (task 1.2): which step each customer is at,
and what the bot answers.

The steps, in order:
  new      -> the customer's first message: welcome + design buttons
  design   -> waiting for the customer to pick a design
  cover_photo -> waiting for 1 photo for the cover (task 2.2). It is also used
              inside the album. Its number is kept in the notes as "cover_photo:N".
  cover_check -> (task 2.5) the cover photo arrived: "got it, checking…". The bot
              checks it in the background (cover_check.py) and calls cover_checked().
              Photos sent meanwhile are counted as album photos.
              Good -> "photos" (or back to the summary). Too small or blurry ->
  cover_problem -> buttons [send another photo] [continue with this one].
              Continuing adds the note "cover_kept": the album shows it smaller.
              The photo being checked is "cover_check:N"; it becomes the cover
              ("cover_photo:N") only once it is accepted.
  photos   -> waiting for photos, until the customer taps "done"
  cover    -> asking: do you want a title on the cover?
  title    -> waiting for the customer to type the title
  done     -> everything is collected; the album is "in the works".
              The summary has two buttons: "all correct" (a short thank-you) and
              "change something", which opens a list (title, design, cover photo,
              add photos): that goes back to the "title", "design", "cover_photo"
              or "photos" step, then straight to a new summary.
  The cover-title question and the title step also have an "add photos" button,
  for customers who tapped "done" too early.
  hd_question -> (task 2.2) most photos came without HD: resend them, or continue?
                 Set by album_job.py after it checks the photos, not by answer().
  After the album is built, album_job.py sends the preview images (task 2.4) and
  adds the note "previews_sent". The last preview message has the buttons
  "love it" (a short thank-you; payment comes in task 3.2) and "change something"
  (the same list as in the summary; the album is then built and sent again).

This file only decides WHAT to answer. It doesn't talk to WhatsApp itself
(bot.py does that), so it can be tested on any computer with no internet.

Every answer is a list of messages. A message is a dict:
  {"text": "...", "buttons": [{"id": "...", "title": "..."}]}   ("buttons" is optional)
or, for a WhatsApp list (one button that opens up to 10 choices):
  {"text": "...", "list": {"button": "...", "rows": [{"id": "...", "title": "..."}]}}

All customer-facing words come from server/texts/<language>.json.
Photos are only COUNTED here. Saving them is in orders.py (task 1.3).
"""

import unicodedata

# The two album designs. Their names for the customer are in the texts file
# ("design_classic", "design_colorful").
DESIGNS = ["classic", "colorful"]
MAX_PHOTOS = 100
# Fewer photos than this: when "done" is tapped, ask once whether to add more
# (it's often an accidental tap). The customer can still continue.
FEW_PHOTOS = 40
MAX_TITLE_LENGTH = 40
# Unicode kinds of characters the album can't print: emojis and other symbols
# (So, Sk), and invisible joiners (Cs, Co). ₪ (Sc) and + (Sm) stay.
_NOT_PRINTABLE = {"So", "Sk", "Cs", "Co"}


def new_state():
    """A fresh customer: no design, no photos yet."""
    return {"step": "new", "design": None, "photos": 0, "title": None, "notes": []}


def read_message(message):
    """Turn one WhatsApp message (as Meta sends it) into (kind, value).

    kind is one of: "text", "button", "photo", "other".
    For a photo, value is {"id": ..., "mime_type": ...}: what we need to
    download it from WhatsApp.
    """
    kind = message.get("type")
    if kind == "text":
        return "text", message.get("text", {}).get("body", "")
    if kind == "interactive":
        # A tapped button, or a choice from a list: both are handled the same way.
        interactive = message.get("interactive", {})
        reply = interactive.get("button_reply") or interactive.get("list_reply") or {}
        return "button", reply.get("id", "")
    if kind == "image":
        return "photo", _media(message.get("image", {}))
    # A photo sent "as a file" (also keeps full quality) arrives as a document.
    if kind == "document" and message.get("document", {}).get("mime_type", "").startswith("image/"):
        return "photo", _media(message["document"])
    return "other", kind


def answer(state, kind, value, texts):
    """Update the customer's state and return the messages to send back."""
    t = texts
    words = _clean(value) if kind == "text" else ""

    # "אלבום חדש" (or similar) at any time starts over.
    if words in _word_list(t, "restart_words") and state["step"] != "new":
        state.clear()
        state.update(new_state())

    step = state["step"]

    if step == "new":
        state["step"] = "design"
        if kind == "photo":
            state["photos"] += 1
            # The design buttons below already ask them to choose; don't nag again.
            state["notes"].append("photo_before_design")
        return [_text(t["welcome"]), _design_buttons(t, t["choose_design"])]

    if kind == "photo":
        return _on_photo(state, t)

    if step == "design":
        design = _pick_design(kind, value, words, t)
        if design is None:
            return [_design_buttons(t, t["choose_design_again"])]
        state["design"] = design
        if "editing" in state["notes"]:
            # They came back from the summary to change the design.
            return _finish(state, t)
        messages = [_text(t["design_chosen"].format(
            design=t["design_" + design], max=MAX_PHOTOS))]
        if state["photos"]:
            # They sent photos before choosing a design: the first one is the cover.
            set_cover_photo(state, 1)
            state["step"] = "photos"
            messages[0] = _text(messages[0]["text"].rsplit("\n\n", 1)[0])
            messages.append(_done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"]))))
        else:
            state["step"] = "cover_photo"
        return messages

    if step == "cover_check":
        return [_text(t["cover_still_checking"])]

    if step == "cover_problem":
        if _tapped(kind, value, words, "cover_new", t["button_cover_new"]) or \
                _tapped(kind, value, words, "cover_new", t["button_cover_new_hd"]):
            state["step"] = "cover_photo"
            _set_note(state, "cover_check", None)
            _set_note(state, "cover_problem", None)
            if "editing" in state["notes"]:
                return [_keep_cover_button(t, t["ask_new_cover_photo"])]
            return [_text(t["ask_cover_photo"])]
        if _tapped(kind, value, words, "cover_keep", t["button_cover_keep"]):
            return _cover_accepted(state, t, kept=True)
        return [cover_problem_message(t, _note(state, "cover_problem"))]

    if step == "cover_photo":
        if "editing" in state["notes"]:
            if (kind == "button" and value == "keep_cover") or words == _clean(t["button_keep_cover"]):
                return _finish(state, t)
            return [_keep_cover_button(t, t["ask_new_cover_photo"])]
        return [_text(t["ask_cover_photo"])]

    if step == "photos":
        few_ok = _tapped(kind, value, words, "few_photos_ok", t["button_few_photos_ok"])
        if few_ok:
            state["notes"].append("few_photos_ok")
        if few_ok or (kind == "button" and value == "photos_done") or words in _word_list(t, "done_words"):
            if state["photos"] == 0:
                return [_text(t["no_photos_yet"])]
            if state["photos"] == 1 and cover_photo(state) == 1:
                # Only the cover photo so far: that's not an album yet.
                return [_done_button(t, t["only_cover_photo"])]
            if state["photos"] < FEW_PHOTOS and "few_photos_ok" not in state["notes"]:
                return [_few_photos_buttons(t, state)]
            if "cover_asked" in state["notes"]:
                # They already answered about the cover (they're resending photos in HD).
                return _finish(state, t)
            state["step"] = "cover"
            state["notes"].append("cover_asked")
            return [_cover_buttons(t, state)]
        if _tapped(kind, value, words, "add_photos", t["button_add_photos"]):
            return [_done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"])))]
        if kind == "other":
            return _once(state, "not_a_photo", [_done_button(t, t["not_a_photo"])])
        return [_done_button(t, t["photos_reminder"])]

    if _tapped(kind, value, words, "add_photos", t["button_add_photos"]) and step in ("cover", "title"):
        # They tapped "done" too early: back to sending photos.
        return _back_to_photos(state, t)

    if step == "cover":
        if (kind == "button" and value == "cover_no") or words in _word_list(t, "no_words"):
            state["title"] = None
            return _finish(state, t)
        if (kind == "button" and value == "cover_yes") or words in _word_list(t, "yes_words"):
            state["step"] = "title"
            return [_title_request(t)]
        if kind == "text" and words:
            # They typed something instead of tapping: that's probably the title.
            return _save_title(state, value, t)
        return [_cover_buttons(t, state)]

    if step == "title":
        if kind == "button" and value == "cover_no":
            state["title"] = None
            return _finish(state, t)
        if kind == "text" and words:
            return _save_title(state, value, t)
        return [_title_request(t)]

    if step == "hd_question":
        if (kind == "button" and value == "hd_continue") or words == _clean(t["button_hd_continue"]):
            state["step"] = "done"
            return [_text(t["hd_continue"])]
        if (kind == "button" and value == "hd_help") or words == _clean(t["button_hd_help"]):
            _resend_photos(state)
            return [_done_button(t, t["hd_how_to"].format(max=MAX_PHOTOS))]
        return [hd_question(t)]

    # step == "done"
    if (kind == "button" and value == "edit_title") or words == _clean(t["button_edit_title"]):
        state["step"] = "title"
        state["notes"].append("editing")
        return [_title_request(t)]
    if (kind == "button" and value == "edit_design") or words == _clean(t["button_edit_design"]):
        state["step"] = "design"
        state["notes"].append("editing")
        return [_design_buttons(t, t["choose_design"])]
    if (kind == "button" and value == "edit_cover") or words == _clean(t["button_edit_cover"]):
        state["step"] = "cover_photo"
        state["notes"].append("editing")
        return [_keep_cover_button(t, t["ask_new_cover_photo"])]
    if _tapped(kind, value, words, "add_photos", t["button_add_photos"]):
        return _back_to_photos(state, t)
    if _tapped(kind, value, words, "edit_menu", t["button_edit"]):
        return [_edit_list(t, t["choose_edit"])]
    if _tapped(kind, value, words, "confirm", t["button_confirm"]):
        if "previews_sent" in state["notes"]:
            # The old summary button, tapped after the previews: same as "love it".
            return _once(state, "preview_ok", [_text(t["preview_ok"])])
        if "confirmed" in state["notes"]:
            return []
        state["notes"].append("confirmed")
        return [_text(t["confirmed"])]
    if _tapped(kind, value, words, "preview_ok", t["button_preview_ok"]):
        return _once(state, "preview_ok", [_text(t["preview_ok"])])
    return _after_done(state, t)


def cover_photo(state):
    """The number of the photo the customer chose for the cover, or None."""
    number = _note(state, "cover_photo")
    return None if number is None else int(number)


def set_cover_photo(state, number):
    _set_note(state, "cover_photo", number)


def checking_cover(state):
    """The number of the cover photo being checked (step "cover_check"), or None."""
    number = _note(state, "cover_check")
    return None if number is None or state["step"] != "cover_check" else int(number)


def cover_checked(state, number, result, t):
    """The cover check (task 2.5) is done: the messages to send.
    result is {"ok", "problem", "without_hd", ...} from album/check_cover.py, or
    None if it couldn't be checked (then the photo is accepted: the album
    still shows a too-small photo smaller, and the owner checks every album).
    Returns [] if the customer has meanwhile moved on."""
    if checking_cover(state) != number:
        return []
    if not result or result.get("ok"):
        return _cover_accepted(state, t, kept=False)
    problem = result.get("problem") or "small"
    if problem == "small" and result.get("without_hd"):
        problem = "small_hd"
    state["step"] = "cover_problem"
    _set_note(state, "cover_problem", problem)
    return [cover_problem_message(t, problem)]


def cover_problem_message(t, problem):
    """The cover photo is too small or blurry: send another, or continue with it?"""
    problem = problem if problem in ("small", "small_hd", "blurry") else "small"
    new = t["button_cover_new_hd"] if problem == "small_hd" else t["button_cover_new"]
    return {"text": t["cover_problem_" + problem], "buttons": [
        {"id": "cover_new", "title": new},
        {"id": "cover_keep", "title": t["button_cover_keep"]},
    ]}


def after_previews(t):
    """The message after the preview images (sent by album_job.py)."""
    return {"text": t["preview_end"], "buttons": [
        {"id": "preview_ok", "title": t["button_preview_ok"]},
        {"id": "edit_menu", "title": t["button_edit"]},
    ]}


def hd_question(t):
    """Most photos came without HD: ask to resend them (sent by album_job.py)."""
    return {"text": t["hd_question"], "buttons": [
        {"id": "hd_help", "title": t["button_hd_help"]},
        {"id": "hd_continue", "title": t["button_hd_continue"]},
    ]}


def left_out_message(left_out, t):
    """One short message about photos left out of the album, e.g.
    "3 blurry and 2 repeated photos were left out". None if nothing was left out.
    left_out is {"blurry": 3, "duplicate": 2, "unusable": 0}."""
    parts = []
    for reason in ("blurry", "duplicate", "unusable"):
        count = left_out.get(reason, 0)
        if count:
            one, many = t["left_out_" + reason]
            parts.append(one if count == 1 else many.format(count=count))
    if not parts:
        return None
    if len(parts) > 1:
        last = parts.pop()
        # Hebrew "and" sticks to the next word; before a number it takes a dash: ו-2
        joined = t["and"] + ("-" if last[0].isdigit() else "") + last
        parts = [", ".join(parts) + " " + joined]
    total = sum(left_out.values())
    verb = t["left_out_verb_one"] if total == 1 else t["left_out_verb_many"]
    return t["left_out"].format(list=parts[0], verb=verb)


# ---------- helpers ----------

def _media(media):
    return {"id": media.get("id"), "mime_type": media.get("mime_type")}


def _on_photo(state, t):
    step = state["step"]
    if step == "hd_question":
        # They're already sending the photos again, in HD.
        _resend_photos(state)
        state["photos"] = 1
        return [_done_button(t, t["hd_resending"])]
    if step == "done":
        return _after_done(state, t)
    if step in ("cover_photo", "cover_problem"):
        # The cover photo is also an album photo. A new cover chosen from the
        # summary may go one over the limit; the old cover stays inside.
        # (In "cover_problem", a photo instead of a tap is the new cover photo.)
        state["photos"] += 1
        state["step"] = "cover_check"
        _set_note(state, "cover_check", state["photos"])
        _set_note(state, "cover_problem", None)
        return [_text(t["cover_checking"])]
    if step == "cover_check" and state["photos"] < MAX_PHOTOS:
        # The rest of the album, sent while the cover is checked: counted quietly.
        state["photos"] += 1
        return []
    if state["photos"] >= MAX_PHOTOS:
        return _once(state, "photo_limit", [_done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))])
    state["photos"] += 1
    if step == "design":
        return _once(state, "photo_before_design", [_design_buttons(t, t["photo_before_design"])])
    if step == "photos" and state["photos"] == 1:
        return [_done_button(t, t["first_photo"])]
    # Customers send many photos; we stay quiet instead of answering each one.
    return []


def _cover_accepted(state, t, kept):
    """The photo being checked becomes the cover (it's fine, or the customer kept it)."""
    set_cover_photo(state, _note(state, "cover_check"))
    _set_note(state, "cover_check", None)
    _set_note(state, "cover_problem", None)
    while "cover_kept" in state["notes"]:
        state["notes"].remove("cover_kept")
    if kept:
        state["notes"].append("cover_kept")   # the album shows it smaller, so it stays sharp
    if "editing" in state["notes"]:
        return _finish(state, t)
    state["step"] = "photos"
    text = t["cover_kept"] if kept else t["cover_photo_saved"]
    return [_done_button(t, text.format(max=MAX_PHOTOS))]


def _note(state, name):
    """The value of a "name:value" note, or None."""
    for note in state["notes"]:
        if note.startswith(name + ":"):
            return note.split(":", 1)[1]
    return None


def _set_note(state, name, value):
    """Set (or with None, remove) a "name:value" note."""
    state["notes"][:] = [n for n in state["notes"] if not n.startswith(name + ":")]
    if value is not None:
        state["notes"].append(f"{name}:{value}")


def _after_done(state, t):
    """The customer wrote (or sent a photo) after everything was collected."""
    if "previews_sent" in state["notes"]:
        return _once(state, "after_previews", [after_previews(t)])
    return _once(state, "after_done", [_change_button(t, t["after_done"])])


def _tapped(kind, value, words, button_id, button_title):
    return (kind == "button" and value == button_id) or (kind == "text" and words == _clean(button_title))


def _back_to_photos(state, t):
    """Let the customer send more photos (from the cover question or the summary)."""
    from_summary = state["step"] == "done" or "editing" in state["notes"]
    state["step"] = "photos"
    if not from_summary and "cover_asked" in state["notes"]:
        # They haven't answered about the title yet: ask again after the photos.
        state["notes"].remove("cover_asked")
    if state["photos"] >= MAX_PHOTOS:
        return [_done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))]
    return [_done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"])))]


def _resend_photos(state):
    """Start the photos over. orders.py sees "resend_photos" and deletes the old ones."""
    state["step"] = "photos"
    state["photos"] = 0
    state["resend_photos"] = True
    set_cover_photo(state, None)   # the album picks a cover from the new photos
    _set_note(state, "cover_check", None)
    _set_note(state, "cover_problem", None)
    for note in ("photo_limit", "not_a_photo", "cover_kept"):
        if note in state["notes"]:
            state["notes"].remove(note)


def _pick_design(kind, value, words, t):
    if kind == "button" and value.startswith("design_") and value[7:] in DESIGNS:
        return value[7:]
    if kind == "text":
        for number, design in enumerate(DESIGNS, start=1):
            if words in (str(number), _clean(t["design_" + design])):
                return design
    return None


def printable(text):
    """The text without emojis and symbols: the album's fonts can't print them
    (they would show as an empty box on the cover). Letters, digits, punctuation
    and Hebrew vowel marks stay. Also tidies extra spaces and line breaks."""
    kept = "".join(c for c in text if unicodedata.category(c) not in _NOT_PRINTABLE
                   and c not in "\ufe0e\ufe0f\u200d\u20e3")
    return " ".join(kept.split())


def _save_title(state, value, t):
    title = printable(value)
    if not title:
        # Only emojis: there's nothing we can print.
        state["step"] = "title"
        return [_title_request(t)]
    if len(title) > MAX_TITLE_LENGTH:
        state["step"] = "title"
        return [_text(t["title_too_long"].format(length=len(title), max=MAX_TITLE_LENGTH))]
    state["title"] = title
    return _finish(state, t)


def _finish(state, t):
    state["step"] = "done"
    # The album is built again, and its new previews are sent.
    for note in ("editing", "after_done", "confirmed", "previews_sent",
                 "after_previews", "preview_ok"):
        while note in state["notes"]:
            state["notes"].remove(note)
    summary = t["summary"].format(
        design=t["design_" + state["design"]],
        count=state["photos"],
        title=state["title"] or t["no_title"],
    )
    return [{"text": summary, "buttons": [
        {"id": "confirm", "title": t["button_confirm"]},
        {"id": "edit_menu", "title": t["button_edit"]},
    ]}]


def _photos(t, count):
    """"תמונה אחת" or "12 תמונות": correct Hebrew for any number."""
    return t["photos_one"] if count == 1 else t["photos_many"].format(count=count)


def _few_photos_buttons(t, state):
    return {"text": t["few_photos"].format(photos=_photos(t, state["photos"]), few=FEW_PHOTOS),
            "buttons": [
                {"id": "add_photos", "title": t["button_add_photos"]},
                {"id": "few_photos_ok", "title": t["button_few_photos_ok"]},
            ]}


def _once(state, note, messages):
    """Send these messages only the first time (so 50 photos don't get 50 replies)."""
    if note in state["notes"]:
        return []
    state["notes"].append(note)
    return messages


def _clean(text):
    return " ".join((text or "").split()).strip(" .!?").lower()


def _word_list(t, key):
    return [_clean(word) for word in t.get(key, [])]


def _text(text):
    return {"text": text}


def _design_buttons(t, text):
    return {"text": text, "buttons": [
        {"id": "design_" + design, "title": t["design_" + design]} for design in DESIGNS
    ]}


def _change_button(t, text):
    return {"text": text, "buttons": [{"id": "edit_menu", "title": t["button_edit"]}]}


def _edit_list(t, text):
    """The "change something" list (WhatsApp allows only 3 buttons,
    so the 4 choices are in a list that opens from one button)."""
    return {"text": text, "list": {"button": t["button_edit"], "title": t["edit_list_title"], "rows": [
        {"id": "edit_title", "title": t["button_edit_title"]},
        {"id": "edit_design", "title": t["button_edit_design"]},
        {"id": "edit_cover", "title": t["button_edit_cover"]},
        {"id": "add_photos", "title": t["button_add_photos"]},
    ]}}


def _keep_cover_button(t, text):
    return {"text": text, "buttons": [{"id": "keep_cover", "title": t["button_keep_cover"]}]}


def _done_button(t, text):
    return {"text": text, "buttons": [{"id": "photos_done", "title": t["button_photos_done"]}]}


def _cover_buttons(t, state):
    return {"text": t["ask_cover"].format(photos=_photos(t, state["photos"])), "buttons": [
        {"id": "cover_yes", "title": t["button_cover_yes"]},
        {"id": "cover_no", "title": t["button_cover_no"]},
        {"id": "add_photos", "title": t["button_add_photos"]},
    ]}


def _title_request(t):
    return {"text": t["ask_title"].format(max=MAX_TITLE_LENGTH), "buttons": [
        {"id": "cover_no", "title": t["button_cover_no"]},
        {"id": "add_photos", "title": t["button_add_photos"]},
    ]}
