"""The customer conversation (task 1.2): which step each customer is at,
and what the bot answers.

The steps, in order:
  new      -> the customer's first message: welcome + design buttons
  design   -> waiting for the customer to pick a design
  cover_photo -> waiting for 1 photo for the cover (task 2.2). It is NOT used
              again inside the album (nor copies of it). Its number is kept in the notes as "cover_photo:N".
  cover_check -> (task 2.5) the cover photo arrived: "got it, checking…". The bot
              checks it in the background (cover_check.py) and calls cover_checked().
              Photos sent meanwhile are counted as album photos.
              Good -> "photos" (or back to the summary). Too small or blurry ->
  cover_problem -> buttons [send another photo] [continue with this one].
              Continuing adds the note "cover_kept": the album shows it smaller.
              The photo being checked is "cover_check:N"; it becomes the cover
              ("cover_photo:N") only once it is accepted.
  photos   -> waiting for photos. The bot stays quiet while they arrive; once no
              photo came for a minute, orders.py calls photos_settled(), which sends
              "got N photos, send more or tap done" with the "done" button (note
              "counted:N"), so the button is BELOW the photos, never above them.
              If "done" is typed while photos still arrive (orders.py sets
              "recent_photo"), the bot says "making sure all photos arrived…"
              (note "done_waiting") and goes on in photos_settled().
  cover    -> asking: do you want a title on the cover?
  title    -> waiting for the customer to type the title
  done     -> everything is collected; the album is "in the works".
              The summary has NO buttons (task 1.2b, owner's test: "הכל נכון?"
              looked like a gate, but the album is built at once anyway). It says
              the link comes soon and changes are made there. After the previews,
              "change something" opens a list (title, design, cover photo, add
              photos, "↩️ בלי שינוי"): that goes back to the "title", "design",
              "cover_photo" or "photos" step, then straight to a new summary.
              Every change step also has "↩️ בלי שינוי" (button id "no_change";
              the cover step's "keep_cover" does the same): back to the album's
              buttons, and the album is NOT built again (state["unchanged"]).
  The cover-title question also has an "add photos" button, for customers who
  tapped "done" too early. The title step has only "no title" (task 1.2b).
  hd_question -> most photos came without HD: resend them, or continue?
                 Asked as soon as the photos stop arriving (task 1.2b: orders.py
                 reads each saved photo's size and calls photos_settled() with
                 without_hd=True), in the same message as the photo count; note
                 "hd_early". "Continue without HD" then goes back to the photos
                 step with the "done" button. If the sizes weren't known in time,
                 album_job.py still asks after the summary (task 2.2).
                 "How do I send HD?" only shows the how-to (with the video clip) and
                 [continue without HD]; nothing is deleted until the first new photo
                 arrives, which replaces the old ones.
  Videos sent with the photos aren't answered one by one: the photo count
  message says once that videos don't go into the album (note "video_untold").
  Starting over: typing "אלבום חדש", or the "🔄 להתחיל מחדש" button (added to every
  message with fewer than 3 buttons once there is something to lose, and to the
  "change something" list). It always asks first [yes, start over] [no, continue],
  because the photos are deleted. A finished album is kept (orders.py).
  After the album is built, album_job.py sends the preview images (task 2.4) and
  adds the note "previews_sent". The last preview message has the buttons
  "love it" and "change something" (the same list as in the summary; the album
  is then built and sent again).
  Owner approval (task 3.1): "love it" adds the note "preview_ok" and sets
  state["ask_owner"], so orders.py asks the owner (owner_approval.py). While the
  owner checks, the notes are "owner_check" + "owner_token:<code>"; the owner's
  answer adds "approved" or "owner_problem". From "love it" on, anything the
  customer types is passed to the owner (state["for_owner"]). Any change to the
  album clears all of these: the album is built again and needs a new approval.

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

from settings import MEDIA_DIR

# The two album designs. Their names for the customer are in the texts file
# ("design_classic", "design_colorful").
DESIGNS = ["classic", "colorful"]
MAX_PHOTOS = 100
# Fewer photos than this: when "done" is tapped, ask once whether to add more
# (it's often an accidental tap). The customer can still continue.
FEW_PHOTOS = 40
MAX_TITLE_LENGTH = 40
# The HD how-to clip (owner's iPhone screen recording, HD button circled).
# Used for every customer for now; an Android clip may come later.
HD_VIDEO = MEDIA_DIR / "hd-how-to-iphone.mp4"
# Notes about the finished album, cleared whenever the album changes (it is
# built again, sent again, and needs the owner's approval again).
ALBUM_NOTES = ("previews_sent", "after_previews", "preview_ok", "after_done",
               "owner_check", "owner_problem", "approved")
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
    if kind == "other" and value == "unsupported":
        # WhatsApp sends this e.g. for the "album" bundle of many photos sent
        # together; the photos themselves arrive one by one. Nothing to answer.
        return []
    restart = _restart(state, kind, value, words, t)
    if restart is not None:
        return restart
    return [with_restart(state, m, t) for m in _answer(state, kind, value, words, t)]


def _answer(state, kind, value, words, t):
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

    if _changing(state) and (_tapped(kind, value, words, "no_change", t["button_no_change"])
                             or _tapped(kind, value, words, "keep_cover", t["button_keep_cover"])):
        return _no_change(state, t)

    if step == "design":
        design = _pick_design(kind, value, words, t)
        if design is None:
            return [_design_buttons(t, t["choose_design_again"], editing="editing" in state["notes"])]
        state["design"] = design
        if "editing" in state["notes"]:
            # They came back from the summary to change the design.
            return _finish(state, t)
        messages = [_with_hd_video(_text(t["design_chosen"].format(
            design=t["design_" + design], max=MAX_PHOTOS)))]
        if state["photos"]:
            # They sent photos before choosing a design: the first one is the cover.
            set_cover_photo(state, 1)
            state["step"] = "photos"
            messages[0]["text"] = messages[0]["text"].rsplit("\n\n", 1)[0]
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
            return [_keep_cover_button(t, t["ask_new_cover_photo"])]
        return [_text(t["ask_cover_photo"])]

    if step == "photos":
        few_ok = _tapped(kind, value, words, "few_photos_ok", t["button_few_photos_ok"])
        if few_ok:
            state["notes"].append("few_photos_ok")
        if few_ok or (kind == "button" and value == "photos_done") or words in _word_list(t, "done_words"):
            if "done_waiting" in state["notes"]:
                return []   # already waiting for the last photos
            if state.get("recent_photo"):
                # Photos are still arriving (many HD photos take a while to upload):
                # wait until they stop, so the count and the album are complete.
                state["notes"].append("done_waiting")
                return [_text(t["photos_wait"])]
            return _photos_done(state, t)
        if _tapped(kind, value, words, "add_photos", t["button_add_photos"]):
            return [_done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"])))]
        if kind == "other":
            # Usually sent in the middle of the photos: no "done" button here.
            if value == "video" and state.get("recent_photo") and "video" not in state["notes"]:
                # Sent with the photos: the count message will say it (one message
                # instead of two, with a silence between them; owner's test, task 1.2b).
                state["notes"] += ["video", "video_untold"]
                return []
            note = "video" if value == "video" else "not_a_photo"
            text = t["video_not_used"] if value == "video" else t["not_a_photo"]
            return _once(state, note, [_text(text)])
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
        return [_title_request(t, "editing" in state["notes"])]

    if step == "hd_question":
        if (kind == "button" and value == "hd_continue") or \
                words in (_clean(t["button_hd_continue"]), _clean(t["button_hd_continue_no_hd"])):
            if "hd_early" in state["notes"]:
                # Asked with the photo count: back to the photos, with the "done" button.
                state["notes"].remove("hd_early")
                state["step"] = "photos"
                _set_note(state, "counted", state["photos"])
                return [_done_button(t, t["hd_continue_photos"].format(
                    photos=_photos(t, state["photos"])))]
            state["step"] = "done"
            return [_text(t["hd_continue"])]
        if (kind == "button" and value == "hd_help") or words == _clean(t["button_hd_help"]):
            # Only the how-to: nothing is deleted until the first new photo arrives,
            # so they can still change their mind and continue without HD.
            return [_hd_how_to(t, state)]
        return [_hd_question_for(state, t)]

    # step == "done"
    if (kind == "button" and value == "edit_title") or words == _clean(t["button_edit_title"]):
        state["step"] = "title"
        _start_change(state)
        return [_title_request(t, editing=True)]
    if (kind == "button" and value == "edit_design") or words == _clean(t["button_edit_design"]):
        state["step"] = "design"
        _start_change(state)
        return [_design_buttons(t, t["choose_design"], editing=True)]
    if (kind == "button" and value == "edit_cover") or words == _clean(t["button_edit_cover"]):
        state["step"] = "cover_photo"
        _start_change(state)
        return [_keep_cover_button(t, t["ask_new_cover_photo"])]
    if _tapped(kind, value, words, "add_photos", t["button_add_photos"]):
        return _back_to_photos(state, t)
    if _tapped(kind, value, words, "no_change", t["button_no_change"]):
        return _no_change(state, t)   # from the list: nothing to change after all
    if _tapped(kind, value, words, "edit_menu", t["button_edit"]):
        return [_edit_list(t, t["choose_edit"])]
    if _tapped(kind, value, words, "confirm", t["button_confirm"]):
        if "previews_sent" in state["notes"]:
            # The old summary button, tapped after the previews: same as "love it".
            return _loved(state, t)
        if "confirmed" in state["notes"]:
            return []
        state["notes"].append("confirmed")
        return [_change_button(t, t["confirmed"])]
    if _tapped(kind, value, words, "preview_ok", t["button_preview_ok"]):
        return _loved(state, t)
    if kind == "text" and words and "preview_ok" in state["notes"]:
        # After "love it", the owner is in the loop (task 3.1): pass it on.
        state["for_owner"] = value.strip()
        return [_text(t["sent_to_team"])]
    return _after_done(state, t)


def _loved(state, t):
    """The customer loves the album: ask the owner to approve it (task 3.1)."""
    if "preview_ok" in state["notes"]:
        return []
    state["notes"].append("preview_ok")
    state["ask_owner"] = True   # orders.py sees this and asks the owner
    return [_text(t["preview_ok"])]


def photos_settled(state, t, without_hd=False):
    """No new photo came for a while (called by orders.py). If "done" was already
    typed, go on to the next question; otherwise send the photo count with the
    "done" button, below the photos. [] if there is nothing new to say.
    without_hd: most photos came without HD (orders.py read their sizes), so the
    count message asks to resend them in HD instead (once per order)."""
    waiting = "done_waiting" in state["notes"]
    if waiting:
        state["notes"].remove("done_waiting")
    count = state["photos"]
    if without_hd and state["step"] == "photos" and "hd_asked" not in state["notes"] \
            and count and not (count == 1 and cover_photo(state) == 1):
        state["step"] = "hd_question"
        state["notes"] += ["hd_asked", "hd_early"]
        _set_note(state, "counted", count)
        return [with_restart(state, _with_videos(state, t, _hd_question_for(state, t)), t)]
    if waiting:
        if state["step"] != "photos":
            return []
        return [with_restart(state, _with_videos(state, t, m), t) for m in _photos_done(state, t)]
    if state["step"] != "photos" or count == 0 or _note(state, "counted") == str(count):
        return []
    if count == 1 and cover_photo(state) == 1:
        return []   # only the cover so far: the bot already asked for the rest
    _set_note(state, "counted", count)
    if count >= MAX_PHOTOS:
        message = _done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))
    elif count < FEW_PHOTOS:
        # Says "we recommend at least 40" here, so "done" won't ask about it again.
        _set_note(state, "few_told", count)
        message = _done_button(t, t["photos_count_few"].format(
            photos=_photos(t, count), few=FEW_PHOTOS))
    else:
        message = _done_button(t, t["photos_count"].format(photos=_photos(t, count)))
    old = _note(state, "resent_from")
    if old and count < MAX_PHOTOS:
        # Sent again in HD: say clearly that the old photos are gone (owner's test).
        first, _, rest = message["text"].partition("\n")
        message = dict(message, text=t["photos_count_resent"].format(
            photos=_photos(t, count), old=old) + "\n" + rest)
    return [with_restart(state, _with_videos(state, t, message), t)]


def _with_videos(state, t, message):
    """Add "videos don't go into the album" under the first line of the message,
    if videos came with the photos and the customer wasn't told yet."""
    if "video_untold" not in state["notes"]:
        return message
    state["notes"].remove("video_untold")
    first, _, rest = message["text"].partition("\n")
    return dict(message, text=first + "\n" + t["videos_skipped"] + ("\n" + rest if rest else ""))


def _photos_done(state, t):
    """The customer has finished sending photos."""
    _set_note(state, "resent_from", None)
    _set_note(state, "photos_at", None)
    if state["photos"] == 0:
        return [_text(t["no_photos_yet"])]
    if state["photos"] == 1 and cover_photo(state) == 1:
        # Only the cover photo so far: that's not an album yet.
        return [_restart_only(t, t["only_cover_photo"])]
    told = _note(state, "few_told") == str(state["photos"])   # the count message said it
    if state["photos"] < FEW_PHOTOS and "few_photos_ok" not in state["notes"] and not told:
        return [_few_photos_buttons(t, state)]
    if "cover_asked" in state["notes"]:
        # They already answered about the cover (they're resending photos in HD).
        return _finish(state, t)
    state["step"] = "cover"
    state["notes"].append("cover_asked")
    return [_cover_buttons(t, state)]


def with_restart(state, message, t):
    """Add the "🔄 להתחיל מחדש" button to a message with fewer than 3 buttons,
    once the customer has something to lose. Not on the summary or the
    previews (there it's in the "change something" list), the restart
    question itself, or the first design question."""
    buttons = message.get("buttons")
    if not buttons or len(buttons) >= 3 or not _has_progress(state):
        return message
    ids = {b["id"] for b in buttons}
    if ids & {"confirm", "preview_ok", "restart_yes", "restart"}:
        return message
    if state["step"] == "design" and "editing" not in state["notes"]:
        return message
    return dict(message, buttons=buttons + [{"id": "restart", "title": t["button_restart"]}])


def _has_progress(state):
    """Is there anything to lose by starting over?"""
    return state["photos"] > 0 or state["step"] not in ("new", "design", "cover_photo")


def _restart(state, kind, value, words, t):
    """Starting over. Returns the messages, or None if this message isn't about it."""
    asked = "confirm_restart" in state["notes"]
    while "confirm_restart" in state["notes"]:
        state["notes"].remove("confirm_restart")   # any other message cancels the question
    wants = (kind == "button" and value == "restart") or words in _word_list(t, "restart_words") \
        or (kind == "text" and words in (_clean(t["button_restart"]), _clean(t["button_restart_list"])))
    yes = _tapped(kind, value, words, "restart_yes", t["button_restart_yes"])
    no = _tapped(kind, value, words, "restart_no", t["button_restart_no"])
    if not (wants or yes or no) or state["step"] == "new":
        return None
    if no:
        return [_text(t["restart_cancelled"])] + [with_restart(state, m, t) for m in _step_prompt(state, t)]
    if (yes and asked) or (wants and not _has_progress(state)):
        state.clear()
        state.update(new_state())
        return _answer(state, "text", "", "", t)   # the welcome and the design buttons
    # Ask first: the photos would be deleted.
    state["notes"].append("confirm_restart")
    finished = state["step"] == "done" or "editing" in state["notes"]
    text = t["restart_confirm_done"] if finished else \
        t["restart_confirm"].format(photos=_photos(t, state["photos"]))
    return [{"text": text, "buttons": [
        {"id": "restart_yes", "title": t["button_restart_yes"]},
        {"id": "restart_no", "title": t["button_restart_no"]},
    ]}]


def _step_prompt(state, t):
    """The question of the step the customer is at (after "no, continue")."""
    step = state["step"]
    if step == "design":
        return [_design_buttons(t, t["choose_design"])]
    if step == "cover_photo":
        if "editing" in state["notes"]:
            return [_keep_cover_button(t, t["ask_new_cover_photo"])]
        return [_text(t["ask_cover_photo"])]
    if step == "cover_check":
        return [_text(t["cover_still_checking"])]
    if step == "cover_problem":
        return [cover_problem_message(t, _note(state, "cover_problem"))]
    if step == "photos":
        return [_done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"])))]
    if step == "cover":
        return [_cover_buttons(t, state)]
    if step == "title":
        return [_title_request(t, "editing" in state["notes"])]
    if step == "hd_question":
        return [_hd_question_for(state, t)]
    if "previews_sent" in state["notes"]:
        return [after_previews(t)]
    return [_summary(state, t)]


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
        return [with_restart(state, m, t) for m in _cover_accepted(state, t, kept=False)]
    problem = result.get("problem") or "small"
    if problem in ("small", "low") and result.get("without_hd"):
        problem += "_hd"
    state["step"] = "cover_problem"
    _set_note(state, "cover_problem", problem)
    return [with_restart(state, cover_problem_message(t, problem), t)]


def cover_problem_message(t, problem):
    """The cover photo is too small or blurry: send another, or continue with it?"""
    if problem not in ("small", "small_hd", "low", "low_hd", "blurry", "shape"):
        problem = "small"
    new = t["button_cover_new_hd"] if problem.endswith("_hd") else t["button_cover_new"]
    message = {"text": t["cover_problem_" + problem], "buttons": [
        {"id": "cover_new", "title": new},
        {"id": "cover_keep", "title": t["button_cover_keep"]},
    ]}
    return _with_hd_video(message) if problem.endswith("_hd") else message


def after_previews(t):
    """The message after the preview images (sent by album_job.py)."""
    return {"text": t["preview_end"], "buttons": [
        {"id": "preview_ok", "title": t["button_preview_ok"]},
        {"id": "edit_menu", "title": t["button_edit"]},
    ]}


def _hd_question_for(state, t):
    if "hd_early" in state["notes"]:
        return {"text": t["hd_question_early"].format(photos=_photos(t, state["photos"])),
                "buttons": hd_question(t)["buttons"]}
    return hd_question(t)


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
        return [_restart_only(t, t["hd_resending"])]
    if step == "done":
        if state["photos"] >= MAX_PHOTOS:
            return _after_done(state, t)
        # A photo that arrives after the summary (still uploading, or sent late):
        # it goes into the album, which is built again (orders.py sees "rebuild").
        state["photos"] += 1
        state["rebuild"] = True
        album_changed(state)
        return _once(state, "late_photos", [_text(t["late_photos"])])
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
    # Customers send many photos; we stay quiet instead of answering each one.
    # Once they stop, photos_settled() sends the count with the "done" button.
    return []


def _cover_accepted(state, t, kept):
    """The photo being checked becomes the cover (it's fine, or the customer kept it)."""
    # "low": a bit less sharp but still fine full size, so it isn't made smaller.
    full_size = (_note(state, "cover_problem") or "").startswith("low")
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
    text = t["cover_photo_saved"]
    if kept:
        text = t["cover_kept_full"] if full_size else t["cover_kept"]
    # No "done" button here: it would be above the photos still to come.
    return [_restart_only(t, text.format(max=MAX_PHOTOS))]


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
    # Before the link: changes are made after seeing the album (task 1.2b).
    return _once(state, "after_done", [_text(t["after_done"])])


def _tapped(kind, value, words, button_id, button_title):
    return (kind == "button" and value == button_id) or (kind == "text" and words == _clean(button_title))


def _back_to_photos(state, t):
    """Let the customer send more photos (from the cover question or the summary)."""
    from_summary = state["step"] == "done" or "editing" in state["notes"]
    state["step"] = "photos"
    if not from_summary and "cover_asked" in state["notes"]:
        # They haven't answered about the title yet: ask again after the photos.
        state["notes"].remove("cover_asked")
    _set_note(state, "counted", state["photos"])   # this message already shows the count
    if state["photos"] >= MAX_PHOTOS:
        return [_done_button(t, t["photo_limit"].format(max=MAX_PHOTOS))]
    message = _done_button(t, t["photos_so_far"].format(photos=_photos(t, state["photos"])))
    if from_summary:
        _set_note(state, "photos_at", state["photos"])   # "no change" = no new photos
        message["buttons"].append(_no_change_button(t))
    return [message]


def _resend_photos(state):
    """Start the photos over. orders.py sees "resend_photos" and deletes the old ones."""
    _set_note(state, "resent_from", state["photos"])   # said in the next count
    state["step"] = "photos"
    state["photos"] = 0
    state["resend_photos"] = True
    set_cover_photo(state, None)   # the album picks a cover from the new photos
    _set_note(state, "counted", None)
    _set_note(state, "cover_check", None)
    _set_note(state, "cover_problem", None)
    for note in ("photo_limit", "not_a_photo", "cover_kept", "hd_early", "video_untold"):
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
    album_changed(state)
    for note in ("editing", "confirmed", "late_photos"):
        while note in state["notes"]:
            state["notes"].remove(note)
    _set_note(state, "photos_at", None)
    return [_summary(state, t)]


def album_changed(state):
    """The album will be built again: forget its previews and approval."""
    state["notes"][:] = [n for n in state["notes"]
                         if n not in ALBUM_NOTES and not n.startswith("owner_token:")]


def _summary(state, t):
    summary = t["summary"].format(
        design=t["design_" + state["design"]],
        count=state["photos"],
        title=state["title"] or t["no_title"],
    )
    # No buttons (task 1.2b): the album is built now; changes come after the link.
    return {"text": summary}


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


def _design_buttons(t, text, editing=False):
    buttons = [{"id": "design_" + design, "title": t["design_" + design]} for design in DESIGNS]
    if editing:
        buttons.append(_no_change_button(t))
    return {"text": text, "buttons": buttons}


def _no_change_button(t):
    return {"id": "no_change", "title": t["button_no_change"]}


def _changing(state):
    """In the middle of a change chosen from the list (or adding photos to a
    finished album)?"""
    return "editing" in state["notes"] or _note(state, "photos_at") is not None


def _start_change(state):
    """A change chosen from the list starts: remember the photo count, so
    "no change" knows whether a photo was sent meanwhile."""
    state["notes"].append("editing")
    _set_note(state, "photos_at", state["photos"])


def _no_change(state, t):
    """ "↩️ בלי שינוי": back to the album's buttons, nothing changes."""
    at = _note(state, "photos_at")
    for name in ("cover_check", "cover_problem"):
        _set_note(state, name, None)   # a new cover photo being checked: dropped
    if at is not None and state["photos"] > int(at):
        # A photo was sent meanwhile: it goes into the album, which is built again.
        if "editing" not in state["notes"]:
            return _photos_done(state, t)
        return _finish(state, t)
    state["notes"][:] = [n for n in state["notes"]
                         if n != "editing" and not n.startswith("photos_at:")]
    state["step"] = "done"
    if "previews_sent" not in state["notes"]:
        return _finish(state, t)        # no link yet: the album is (re)built as usual
    state["unchanged"] = True           # orders.py: don't build the album again
    return [dict(after_previews(t), text=t["no_change_done"])]


def _change_button(t, text):
    return {"text": text, "buttons": [{"id": "edit_menu", "title": t["button_edit"]}]}


def _edit_list(t, text):
    """The "change something" list (WhatsApp allows only 3 buttons,
    so the choices are in a list that opens from one button)."""
    return {"text": text, "list": {"button": t["button_edit"], "title": t["edit_list_title"], "rows": [
        {"id": "edit_title", "title": t["button_edit_title"]},
        {"id": "edit_design", "title": t["button_edit_design"]},
        {"id": "edit_cover", "title": t["button_edit_cover"]},
        {"id": "add_photos", "title": t["button_add_photos"]},
        {"id": "restart", "title": t["button_restart_list"]},
        {"id": "no_change", "title": t["button_no_change"]},
    ]}}


def _keep_cover_button(t, text):
    return {"text": text, "buttons": [_no_change_button(t)]}


def _restart_only(t, text):
    """A message whose only button is "🔄 להתחיל מחדש" (no "done" button above
    photos that are still to come)."""
    return {"text": text, "buttons": [{"id": "restart", "title": t["button_restart"]}]}


def _with_hd_video(message):
    """Put the HD how-to clip on top of the message, if the clip is there."""
    if HD_VIDEO.exists():
        return dict(message, video_file=str(HD_VIDEO))
    return message


def _hd_how_to(t, state):
    return _with_hd_video({"text": t["hd_how_to"].format(
        max=MAX_PHOTOS, photos=_photos(t, state["photos"])), "buttons": [
        {"id": "hd_continue", "title": t["button_hd_continue_no_hd"]},
    ]})


def _done_button(t, text):
    return {"text": text, "buttons": [{"id": "photos_done", "title": t["button_photos_done"]}]}


def _cover_buttons(t, state):
    return {"text": t["ask_cover"].format(photos=_photos(t, state["photos"])), "buttons": [
        {"id": "cover_yes", "title": t["button_cover_yes"]},
        {"id": "cover_no", "title": t["button_cover_no"]},
        {"id": "add_photos", "title": t["button_add_photos"]},
    ]}


def _title_request(t, editing=False):
    # Only "no title" (owner's test, task 1.2b: more buttons here confused people),
    # plus "no change" when changing it after seeing the album.
    buttons = [{"id": "cover_no", "title": t["button_cover_no"]}]
    if editing:
        buttons.append(_no_change_button(t))
    return {"text": t["ask_title"].format(max=MAX_TITLE_LENGTH), "buttons": buttons}
