"""The customer conversation (task 1.2): which step each customer is at,
and what the bot answers.

The steps, in order:
  new      -> the customer's first message: welcome + design buttons
  design   -> waiting for the customer to pick a design
  photos   -> waiting for photos, until the customer taps "done"
  cover    -> asking: do you want a title on the cover?
  title    -> waiting for the customer to type the title
  done     -> everything is collected; the album is "in the works".
              The summary has buttons to change the title or the design: that goes
              back to the "title" or "design" step, then straight to a new summary.
  hd_question -> (task 2.2) most photos came without HD: resend them, or continue?
                 Set by album_job.py after it checks the photos, not by answer().

This file only decides WHAT to answer. It doesn't talk to WhatsApp itself
(bot.py does that), so it can be tested on any computer with no internet.

Every answer is a list of messages. A message is a dict:
  {"text": "...", "buttons": [{"id": "...", "title": "..."}]}   ("buttons" is optional)

All customer-facing words come from server/texts/<language>.json.
Photos are only COUNTED here. Saving them is in orders.py (task 1.3).
"""

# The two album designs. Their names for the customer are in the texts file
# ("design_classic", "design_colorful").
DESIGNS = ["classic", "colorful"]
MAX_PHOTOS = 100
MAX_TITLE_LENGTH = 40


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
        reply = message.get("interactive", {}).get("button_reply") or {}
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
        state["step"] = "photos"
        messages = [_text(t["design_chosen"].format(
            design=t["design_" + design], max=MAX_PHOTOS))]
        if state["photos"]:
            messages.append(_done_button(t, t["photos_so_far"].format(count=state["photos"])))
        return messages

    if step == "photos":
        if (kind == "button" and value == "photos_done") or words in _word_list(t, "done_words"):
            if state["photos"] == 0:
                return [_text(t["no_photos_yet"])]
            if "cover_asked" in state["notes"]:
                # They already answered about the cover (they're resending photos in HD).
                return _finish(state, t)
            state["step"] = "cover"
            state["notes"].append("cover_asked")
            return [_cover_buttons(t, state)]
        if kind == "other":
            return _once(state, "not_a_photo", [_done_button(t, t["not_a_photo"])])
        return [_done_button(t, t["photos_reminder"])]

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
    return _once(state, "after_done", [_edit_buttons(t, t["after_done"])])


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
        return _once(state, "after_done", [_edit_buttons(t, t["after_done"])])
    if state["photos"] >= MAX_PHOTOS:
        return _once(state, "photo_limit", [_done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))])
    state["photos"] += 1
    if step == "design":
        return _once(state, "photo_before_design", [_design_buttons(t, t["photo_before_design"])])
    if step == "photos" and state["photos"] == 1:
        return [_done_button(t, t["first_photo"])]
    # Customers send many photos; we stay quiet instead of answering each one.
    return []


def _resend_photos(state):
    """Start the photos over. orders.py sees "resend_photos" and deletes the old ones."""
    state["step"] = "photos"
    state["photos"] = 0
    state["resend_photos"] = True
    for note in ("photo_limit", "not_a_photo"):
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


def _save_title(state, value, t):
    title = " ".join(value.split())  # tidy extra spaces and line breaks
    if len(title) > MAX_TITLE_LENGTH:
        state["step"] = "title"
        return [_text(t["title_too_long"].format(length=len(title), max=MAX_TITLE_LENGTH))]
    state["title"] = title
    return _finish(state, t)


def _finish(state, t):
    state["step"] = "done"
    for note in ("editing", "after_done"):
        while note in state["notes"]:
            state["notes"].remove(note)
    summary = t["summary"].format(
        design=t["design_" + state["design"]],
        count=state["photos"],
        title=state["title"] or t["no_title"],
    )
    return [_edit_buttons(t, summary)]


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


def _edit_buttons(t, text):
    """The summary's buttons: change the title or the design."""
    return {"text": text, "buttons": [
        {"id": "edit_title", "title": t["button_edit_title"]},
        {"id": "edit_design", "title": t["button_edit_design"]},
    ]}


def _done_button(t, text):
    return {"text": text, "buttons": [{"id": "photos_done", "title": t["button_photos_done"]}]}


def _cover_buttons(t, state):
    return {"text": t["ask_cover"].format(count=state["photos"]), "buttons": [
        {"id": "cover_yes", "title": t["button_cover_yes"]},
        {"id": "cover_no", "title": t["button_cover_no"]},
    ]}


def _title_request(t):
    return {"text": t["ask_title"].format(max=MAX_TITLE_LENGTH),
            "buttons": [{"id": "cover_no", "title": t["button_cover_no"]}]}
