"""The customer conversation (task 1.2): which step each customer is at,
and what the bot answers.

The steps, in order:
  new      -> the customer's first message: welcome + design buttons
  design   -> waiting for the customer to pick a design
  photos   -> waiting for photos, until the customer taps "done"
  cover    -> asking: do you want a title on the cover?
  title    -> waiting for the customer to type the title
  done     -> everything is collected; the album is "in the works"

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
            state["step"] = "cover"
            return [_cover_buttons(t, state)]
        if kind == "other":
            return _once(state, "not_a_photo", [_done_button(t, t["not_a_photo"])])
        return [_done_button(t, t["photos_reminder"])]

    if step == "cover":
        if (kind == "button" and value == "cover_no") or words in _word_list(t, "no_words"):
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
            return _finish(state, t)
        if kind == "text" and words:
            return _save_title(state, value, t)
        return [_title_request(t)]

    # step == "done"
    return _once(state, "after_done", [_text(t["after_done"])])


# ---------- helpers ----------

def _media(media):
    return {"id": media.get("id"), "mime_type": media.get("mime_type")}


def _on_photo(state, t):
    step = state["step"]
    if step == "done":
        return _once(state, "after_done", [_text(t["after_done"])])
    if state["photos"] >= MAX_PHOTOS:
        return _once(state, "photo_limit", [_done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))])
    state["photos"] += 1
    if step == "design":
        return _once(state, "photo_before_design", [_design_buttons(t, t["photo_before_design"])])
    if step == "photos" and state["photos"] == 1:
        return [_done_button(t, t["first_photo"])]
    # Customers send many photos; we stay quiet instead of answering each one.
    return []


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
    summary = t["summary"].format(
        design=t["design_" + state["design"]],
        count=state["photos"],
        title=state["title"] or t["no_title"],
    )
    return [_text(summary)]


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
