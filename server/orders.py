"""Customers' orders and photos (task 1.3).

- Each customer's place in the conversation is kept in memory AND saved in
  Supabase after every message, so restarting the bot (or the Mac) no longer
  starts everyone over.
- Every accepted photo is downloaded from WhatsApp and saved in the private
  Supabase bucket, as <order id>/001.jpg, 002.jpg, ... in the order received.
- If a customer starts a new album before finishing the old one, the old one
  is marked "cancelled" and its photos are deleted.

Task 2.2: when an order is complete, on_ready(phone, order_id) is called, so
album_job.py can check the photos and build the album. The photos still being
saved are counted, so the album waits for them.

Task 2.5: when a cover photo arrives, on_cover(phone, order_id, number) is
called, so cover_check.py can check it as soon as it is saved. Its answer comes
back through cover_checked().

Task 3.1: when the customer loves the album, on_approval(phone, order_id) is
called, so owner_approval.py can ask the owner. Anything the customer types
after that goes to on_customer_text(phone, order_id, text). The owner's answer
is saved here (owner_asked, owner_decided). It is kept in the order's notes
("owner_check", "owner_token:<code>", "approved", "owner_problem"), so no
database change was needed.

Task 3.2: when the customer has sent a shipping address, on_payment(phone,
order_id) is called, so owner_approval.py can ask the owner to send a Bit
payment request by hand. The owner's "payment received" is owner_paid().
The address, the price and the time of payment are saved in the order's own
columns (shipping_address, price, paid_at; supabase/3.2-address-and-payment.sql),
and its status becomes "approved", then "paid".
To check a photo number the customer types, album_numbers(order_id) (set by
bot.py) gives the numbers of the photos inside the album. A question after
"עזרה" goes to on_help(phone, order_id, text).

Task 3.3: every save of an order also records what changed (a new step, a new
note) in the order history (history.py), and the other parts of the bot add
their own moments through record(). Numbers only, never texts or photos.

Task 3.4: cleanup.py deletes old photos by itself. It changes an order through
reload_after(), so the customer's remembered state is read again. A customer
whose unpaid album was deleted ("expired") starts a new album at their next
message, told why first (text "album_expired").

Task 3.3b: every incoming message is recorded too ("message_in": its kind,
the button, whether it changed anything, the text's length only), and where
the customer came from ("source", from bot.py). behaviour.py has the details.

The conversation itself (what to answer) is still in conversation.py.
"""

import copy
import logging
import threading
import time
from datetime import datetime, timezone

import behaviour
import cleanup
import conversation
import history
from database import DatabaseError
from whatsapp import WhatsAppError

log = logging.getLogger("bot")

# WhatsApp allows up to 100 MB for files; we don't need more than this per photo.
# (Must stay at or below the bucket's 50 MB limit.)
MAX_PHOTO_BYTES = 40 * 1024 * 1024
FILE_TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
              "image/heic": "heic", "image/heif": "heif", "image/webp": "webp"}
# Photos have "stopped arriving" once none came for this long. Then the bot sends
# the photo count with the "done" button (below the photos), or, if "done" was
# already typed, goes on. Many HD photos take a while to upload, with pauses.
QUIET_SECONDS = 60
# Before deciding whether to ask about HD (task 1.2b), wait up to this long for
# the photos still being saved, so their sizes are known.
HD_WAIT_SECONDS = 20
# Ask to resend in HD when at least this part of the photos came without it
# (the same rule as album_job.WITHOUT_HD_SHARE), judged on at least this many.
WITHOUT_HD_SHARE = 0.5
HD_MIN_KNOWN = 3
# WhatsApp without HD sends photos exactly this long on the long side
# (album/quality.py WITHOUT_HD_PIXELS, measured Nov 2026).
WITHOUT_HD_PIXELS = 2048
# At most this many new albums per phone number per day (CLAUDE.md rule 11: a
# finished album is kept when the customer starts over, so its photos stay in
# storage; without a limit one person could fill the free 1 GB).
MAX_NEW_ALBUMS_PER_DAY = 3
# Wait a little before deleting a cancelled order's photos, so photos that are
# still uploading get deleted too.
DELETE_DELAY_SECONDS = 60
# Task 3.3b: a source code (ad, link) also counts for an album the customer
# starts within this long after it.
SOURCE_CARRY_SECONDS = 24 * 3600


def short(order_id):
    """The first 8 characters of an order ID: enough to find it in the logs."""
    return (order_id or "?")[:8]


class Orders:
    def __init__(self, db, on_ready=None, on_cover=None):
        self.db = db
        self.on_ready = on_ready   # called as on_ready(phone, order_id) when an order is complete
        # called as on_cover(phone, order_id, number) when a cover photo needs checking
        self.on_cover = on_cover
        self._cover_checks = set()   # (order_id, number) of cover checks already started
        self._states = {}   # phone -> conversation state
        self._locks = {}    # phone -> lock (one message at a time per customer)
        self._guard = threading.Lock()
        self._saving = {}   # order_id -> numbers of the photos still being saved
        self._saved = threading.Condition()
        self.send = None         # send(phone, message), set by bot.py
        self._last_photo = {}    # phone -> when their last photo arrived (time.monotonic)
        self._settling = set()   # phones waiting for their photos to stop arriving
        self._sizes = {}   # order_id -> {photo number: long side in pixels}
        self.on_approval = None        # on_approval(phone, order_id): ask the owner (task 3.1)
        self.on_customer_text = None   # on_customer_text(phone, order_id, text): tell the owner
        self.on_payment = None   # on_payment(phone, order_id): ask the owner to collect (3.2)
        self.on_help = None      # on_help(phone, order_id, text): a "עזרה" question (3.2)
        # album_numbers(order_id) -> the numbers of the photos inside the album, or None
        self.album_numbers = None
        # album_removable(order_id) -> the numbers that may be removed, or None
        self.album_removable = None
        self.history = None   # history.History (task 3.3), set by bot.py
        self._seen = {}       # order_id -> (step, notes) as last recorded
        self._sources = {}    # phone -> (code, details, when) of their last source (3.3b)

    def lock_for(self, phone):
        with self._guard:
            return self._locks.setdefault(phone, threading.Lock())

    def answer(self, phone, kind, value, texts, source=None):
        """Answer one message. Call it while holding lock_for(phone).

        Returns (replies, photo) where photo is None, or (order_id, number) when
        this message is a photo that should be saved.
        Raises DatabaseError only if Supabase can't be reached to find or create
        the customer's order (then nothing has changed).
        source: (code, details) of where the customer came from (task 3.3b).
        The message itself is recorded in the order history ("message_in").
        """
        state = self._load(phone)
        before = _snapshot(state)
        if source and source[0]:
            self._sources[phone] = (source[0], source[1], time.monotonic())
            self.record(state["order_id"], "source", state=state, detail=source[0],
                        info=source[1])
        # A message from one of our links is never an answer (conversation._from_link).
        state["from_link"] = bool(source and source[0] and kind == "text")
        try:
            replies, photo = self._answer(phone, kind, value, texts)
        finally:
            state.pop("from_link", None)
        self._record_message(phone, before, kind, value, replies, photo, texts)
        return replies, photo

    def _record_message(self, phone, before, kind, value, replies, photo, texts):
        """One "message_in" row: what the customer sent (never the text itself)
        and whether it changed anything. Typing where a button was expected and
        changing nothing is a sign of confusion."""
        state = self._states.get(phone)
        if not state:
            return
        changed = photo is not None or _snapshot(state) != before
        wanted = behaviour.expected(before[1], before[2])
        info = {"expected": wanted, "changed": changed,
                "replies": [behaviour.message_name(r, texts) for r in replies][:5]}
        if kind == "button":
            info["button"] = behaviour.button_code(value)
        elif kind == "text":
            info["letters"] = len(value or "")
        elif kind == "other":
            info["type"] = str(value)[:20]
        if state["order_id"] != before[0]:
            info["new_order"] = True
        info["confused"] = kind == "text" and wanted == "button" and not changed
        self.record(state["order_id"], "message_in", state=state, step=before[1],
                    detail=kind, info=info)

    def order_of(self, phone):
        """The customer's current order ID, if the bot has it in memory."""
        state = self._states.get(phone)
        return state["order_id"] if state else None

    def _answer(self, phone, kind, value, texts):
        state = self._load(phone)
        expired = state.pop("expired_before", False)
        old_order, old_step = state["order_id"], state["step"]
        # Changing something from the summary: the album was already finished.
        was_finished = old_step in conversation.FINISHED_STEPS or "editing" in state["notes"]
        count_before = state["photos"]

        last = self._last_photo.get(phone)
        state["recent_photo"] = last is not None and time.monotonic() - last < QUIET_SECONDS
        if state["step"] == "photo_number" and self.album_numbers:
            # The customer is typing a photo's number: check it against the album.
            state["album_numbers"] = self.album_numbers(state["order_id"])
        if state["step"] == "photo_action" and self.album_removable:
            # Removing a photo alone on its page must not make the album too short.
            state["album_removable"] = self.album_removable(state["order_id"])
        before = copy.deepcopy(state)
        state["wa_number"] = phone   # for "📱 this number" (shipping, task 3.2)
        try:
            replies = conversation.answer(state, kind, value, texts)
        finally:
            state.pop("wa_number", None)
            state.pop("recent_photo", None)
            state.pop("album_numbers", None)
            state.pop("album_removable", None)
        if kind == "photo":
            self._last_photo[phone] = time.monotonic()

        asked = "confirm_restart" in state["notes"] and "confirm_restart" not in before["notes"]
        if ("order_id" not in state or asked) and \
                self._albums_today(phone) >= MAX_NEW_ALBUMS_PER_DAY:
            # A new album (or the "are you sure?" before one), but they already
            # started the most albums for today: nothing changes.
            before.pop("recent_photo", None)
            before.pop("album_numbers", None)
            before.pop("album_removable", None)
            before["notes"] = [n for n in before["notes"] if n != "confirm_restart"]
            self._states[phone] = before
            self.record(before["order_id"], "new_album_limit", state=before)
            log.info("Order %s: the customer reached today's new-album limit",
                     short(before["order_id"]))
            return [{"text": texts["new_album_limit"].format(max=MAX_NEW_ALBUMS_PER_DAY)}], None
        if expired:
            # Their last album was deleted after days without payment (task 3.4).
            replies = [{"text": texts["album_expired"].format(days=cleanup.UNPAID_DAYS)}] + replies

        if "order_id" not in state:
            # "אלבום חדש": answer() started a fresh state, so open a new order.
            try:
                state["order_id"] = self._new_order(phone, state)
            except DatabaseError:
                del self._states[phone]  # reload from Supabase next time
                raise
            self.record(old_order, "new_album", detail="kept" if was_finished else "cancelled",
                        photos=count_before)
            if not was_finished:
                self._cancel(old_order)
            return replies, None
        resend = state.pop("resend_photos", False)
        if resend:
            # The customer is sending their photos again in HD: delete the old ones
            # first, so the new photo 1, 2, 3… don't clash with them.
            try:
                # The cover photo stays (owner's test, task 1.2b): it becomes photo 1.
                keep = resend if resend is not True else None
                count = self.db.delete_order_photos(state["order_id"], keep=keep)
                self._sizes.pop(state["order_id"], None)
                self.record(state["order_id"], "photos_deleted_for_hd", count=count, state=state)
                log.info("Deleted %s photos of order %s (resending in HD)",
                         count, short(state["order_id"]))
            except DatabaseError as error:
                log.error("Could not delete old photos of order %s: %s",
                          short(state["order_id"]), error)
        # (If saving fails, the bot still remembers it; the next message saves it again.)
        self._save(state)

        photo = None
        # A new photo was counted (when resending in HD, the first new photo
        # starts the count again at 1, so it's lower than before but still new).
        if kind == "photo" and (state["photos"] > count_before or resend):
            photo = (state["order_id"], state["photos"])
            # Count it as "still saving" BEFORE the album may start: a new cover
            # photo is the very message that completes the order again, and the
            # album must wait for it. The caller saves it, then calls photo_done().
            self.photo_saving(state["order_id"], state["photos"])

        self._check_cover(phone, state)
        if state.pop("ask_owner", False):
            if self.on_approval:
                self.on_approval(phone, state["order_id"])
            else:
                log.warning("Order %s: the customer loved it, but no owner approval is set up",
                            short(state["order_id"]))
        if state.pop("ask_payment", False):
            if self.on_payment:
                self.on_payment(phone, state["order_id"])
            else:
                log.warning("Order %s is waiting for payment, but no owner is set up",
                            short(state["order_id"]))
        question = state.pop("help_for_owner", None)   # "עזרה" (task 3.2)
        if question and self.on_help:
            self.on_help(phone, state["order_id"], question)
        text = state.pop("for_owner", None)
        if text and self.on_customer_text:
            self.on_customer_text(phone, state["order_id"], text)
        rebuild = state.pop("rebuild", False)   # a photo arrived after the summary
        unchanged = state.pop("unchanged", False)   # "↩️ בלי שינוי": the album stays as it is
        if state["step"] == "done" and (old_step != "done" or rebuild) and not unchanged \
                and self.on_ready:
            self.on_ready(phone, state["order_id"])
        if "done_waiting" in state["notes"] or conversation._note(state, "late_from") or \
                (kind == "photo" and state["step"] in ("photos", "cover_check")):
            # (Also photos after the summary, and after a bot restart that
            # happened while late photos were arriving: the count comes once
            # they stop, then the album is built again.)
            self._settle_later(phone, texts)
        return replies, photo

    # ---------- once photos stop arriving: the count, or go on after "done" ----------

    def _settle_later(self, phone, texts):
        with self._guard:
            if phone in self._settling:
                return
            self._settling.add(phone)
        threading.Thread(target=self._settle, args=(phone, texts), daemon=True).start()

    def _settle(self, phone, texts):
        try:
            while True:
                last = self._last_photo.get(phone)
                left = 0 if last is None else QUIET_SECONDS - (time.monotonic() - last)
                if left <= 0:
                    break
                time.sleep(min(left + 0.05, QUIET_SECONDS))
            with self._guard:
                self._settling.discard(phone)
            state = self._states.get(phone)
            if state and state["step"] == "photos":
                # Let the last photos finish saving, so we know how many came without HD.
                self.wait_for_photos(state["order_id"], HD_WAIT_SECONDS)
            with self.lock_for(phone):
                state = self._states.get(phone)
                if not state:
                    return
                old_step = state["step"]
                replies = conversation.photos_settled(
                    state, texts, without_hd=self.mostly_without_hd(state["order_id"]))
                if not replies:
                    return
                self._record_sizes(state)
                self._save(state)
                rebuild = state.pop("rebuild", False)   # photos came after the summary
                if state["step"] == "done" and (old_step != "done" or rebuild) and self.on_ready:
                    self.on_ready(phone, state["order_id"])
            for message in replies:
                if self.send:
                    self.send(phone, message)
        except Exception:
            with self._guard:
                self._settling.discard(phone)
            log.exception("Something went wrong after the photos stopped arriving")

    # ---------- the cover check (task 2.5) ----------

    def _check_cover(self, phone, state):
        """Start checking the cover photo, once. (Also after a restart of the bot,
        when the customer's next message finds them still at "cover_check".)"""
        number = conversation.checking_cover(state)
        key = (state["order_id"], number)
        if number is None or key in self._cover_checks or not self.on_cover:
            return
        self._cover_checks.add(key)
        self.on_cover(phone, state["order_id"], number)

    def cover_checked(self, phone, order_id, number, result, texts):
        """The cover photo's check is done. Returns the messages to send
        ([] if the customer has meanwhile moved on)."""
        with self.lock_for(phone):
            self._cover_checks.discard((order_id, number))
            state = self._states.get(phone)
            if not state or state["order_id"] != order_id:
                return []
            old_step = state["step"]
            replies = conversation.cover_checked(state, number, result, texts)
            if not replies:
                return []
            self._save(state)
            if state["step"] == "done" and old_step != "done" and self.on_ready:
                self.on_ready(phone, order_id)   # a new cover chosen from the summary
            if state["step"] == "photos":
                # Photos sent during the check: their count comes once they stop.
                self._settle_later(phone, texts)
            return replies

    # ---------- for the album (task 2.2) ----------

    def photo_saving(self, order_id, number=None):
        """A photo of this order started saving (answer() calls this itself)."""
        with self._saved:
            self._saving.setdefault(order_id, []).append(number)

    def photo_done(self, order_id, number=None):
        """That photo is saved, or failed for good."""
        with self._saved:
            numbers = self._saving.get(order_id, [])
            if number in numbers:
                numbers.remove(number)
            elif numbers:
                numbers.pop()
            if not numbers:
                self._saving.pop(order_id, None)
            self._saved.notify_all()

    def wait_for_photos(self, order_id, timeout, number=None):
        """Wait until all of the order's photos (or only photo number N) are
        saved. False if it took too long."""
        def saved():
            if number is None:
                return order_id not in self._saving
            return number not in self._saving.get(order_id, [])
        with self._saved:
            return self._saved.wait_for(saved, timeout)

    def photo_size(self, order_id, number, long_side):
        """A photo was saved: remember its size (long side in pixels), to tell
        whether the customer sent without HD (task 1.2b). Nothing else is kept."""
        with self._saved:
            self._sizes.setdefault(order_id, {})[number] = long_side

    def mostly_without_hd(self, order_id):
        """True if most of the order's saved photos came without HD (exactly
        2048 px). False if not, or if too few sizes are known yet (then the album
        check asks later, album_job.py)."""
        with self._saved:
            sizes = [s for s in self._sizes.get(order_id, {}).values() if s]
        if len(sizes) < HD_MIN_KNOWN:
            return False
        without = sum(s == WITHOUT_HD_PIXELS for s in sizes)
        return without >= WITHOUT_HD_SHARE * len(sizes)

    def notes_of(self, phone, order_id):
        """The order's notes, or None if the customer has moved on to another order."""
        with self.lock_for(phone):
            state = self._states.get(phone)
            if not state or state["order_id"] != order_id:
                return None
            return list(state["notes"])

    def ask_hd(self, phone, order_id):
        """Move a finished order to the "resend in HD?" question.
        Returns False if the customer has meanwhile done something else."""
        with self.lock_for(phone):
            state = self._states.get(phone)
            if not state or state["order_id"] != order_id or state["step"] != "done":
                return False
            state["step"] = "hd_question"
            state["notes"].append("hd_asked")
            self._save(state)
            return True

    def is_done(self, phone, order_id):
        """True if this is still the customer's order and they are not in the
        middle of changing something (step "done"), and no photos are still
        arriving after the summary (then the album is built again first)."""
        with self.lock_for(phone):
            state = self._states.get(phone)
            return bool(state and state["order_id"] == order_id and state["step"] == "done"
                        and conversation._note(state, "late_from") is None)

    def add_note(self, phone, order_id, note):
        """Add a note to the order (e.g. "previews_sent", task 2.4) and save it."""
        with self.lock_for(phone):
            state = self._states.get(phone)
            if not state or state["order_id"] != order_id:
                return
            if note not in state["notes"]:
                state["notes"].append(note)
            self._save(state)

    # ---------- the owner's approval (task 3.1) ----------

    def owner_asked(self, phone, order_id, token):
        """The owner is being asked about this order. Returns False if the
        customer has meanwhile changed something (then don't ask)."""
        with self.lock_for(phone):
            state = self._current(phone, order_id)
            if not state or state["step"] != "done" or "preview_ok" not in state["notes"]:
                return False
            notes = [n for n in state["notes"] if not n.startswith("owner_token:")
                     and n not in ("owner_check", "owner_problem", "approved")]
            state["notes"][:] = notes + ["owner_check", "owner_token:" + token]
            self._save(state)
            return True

    def owner_token(self, phone, order_id):
        """The code of the owner's current request for this order, or None."""
        with self.lock_for(phone):
            state = self._current(phone, order_id)
            return _token(state) if state else None

    def owner_decided(self, phone, order_id, token, decision):
        """The owner tapped "approve" or "problem". Returns:
        "ok", "already" (approved before), or "old" (the album changed since,
        or the customer started another album)."""
        with self.lock_for(phone):
            state = self._current(phone, order_id)
            if not state or _token(state) != token:
                return "old"
            if "approved" in state["notes"]:
                return "already"
            if decision == "approved":
                state["notes"][:] = [n for n in state["notes"]
                                     if n not in ("owner_check", "owner_problem")]
                conversation.owner_approved(state)   # next: the shipping address (3.2)
            elif "owner_problem" in state["notes"]:
                return "ok"
            state["notes"].append(decision)
            self._save(state)
            return "ok"

    # ---------- payment (task 3.2) ----------

    def owner_paid(self, phone, order_id):
        """The owner tapped "payment received". Returns "ok", "already" (paid
        before), or "old" (not this customer's current order, or not waiting)."""
        with self.lock_for(phone):
            state = self._current(phone, order_id)
            if not state:
                return "old"
            if state["step"] == "paid":
                return "already"
            if state["step"] != "payment":
                return "old"
            conversation.owner_paid(state)
            self._save(state)
            try:
                self.db.update_order(order_id, {"paid_at": datetime.now(timezone.utc).isoformat()})
            except DatabaseError as error:
                log.error("Could not save the payment time of %s: %s", short(order_id), error)
            return "ok"

    def waiting_for_payment(self):
        """Orders whose customer sent an address and waits for a Bit request:
        [(phone, order_id)], oldest first."""
        rows = self.db.orders_with_note("payment_wait")
        return [(row["phone"], row["id"]) for row in rows if row["status"] != "cancelled"]

    def waiting_for_owner(self):
        """Orders waiting for the owner: [(phone, order_id)], oldest first."""
        rows = self.db.orders_with_note("owner_check")
        return [(row["phone"], row["id"]) for row in rows if row["status"] != "cancelled"]

    def phone_of(self, order_id):
        """The customer's phone number for an order, or None."""
        row = self.db.get_order(order_id)
        return row["phone"] if row else None

    def info(self, phone, order_id):
        """A copy of the order's details (design, title, photos, notes), or None."""
        with self.lock_for(phone):
            state = self._current(phone, order_id)
            return None if not state else dict(state, notes=list(state["notes"]),
                                               ship=dict(state.get("ship") or {}))

    def _current(self, phone, order_id):
        """The customer's state if order_id is still their order (loads it from
        Supabase after a restart), else None."""
        try:
            state = self._load(phone)
        except DatabaseError as error:
            log.error("Could not load the order of %s: %s", short(order_id), error)
            return None
        return state if state["order_id"] == order_id else None

    def _save(self, state):
        try:
            self.db.update_order(state["order_id"], _fields(state))
        except DatabaseError as error:
            log.error("Could not save order %s: %s", short(state["order_id"]), error)
        self._record_changes(state)

    # ---------- the order history (task 3.3) ----------

    def record(self, order_id, event, state=None, **values):
        """Add one moment to the order's history (history.py). state: the
        customer's state, for the step and photo count at that moment.
        Never raises: the history must not get in the customer's way."""
        if not self.history or not order_id:
            return
        if state is not None:
            values.setdefault("step", state.get("step"))
            values.setdefault("photos", state.get("photos"))
        try:
            self.history.record(order_id, event, **values)
        except Exception:
            log.exception("Could not record %s in the order history", event)

    def record_for(self, phone, order_id, event, **values):
        """record(), with the step and photo count of the customer's state
        (for album_job.py, cover_check.py, owner_approval.py)."""
        state = self._states.get(phone)
        if state and state.get("order_id") == order_id:
            values.setdefault("step", state["step"])
            values.setdefault("photos", state["photos"])
        self.record(order_id, event, phone=phone, **values)

    def _record_changes(self, state):
        """Record the order's new step and new notes since it was last saved."""
        order_id = state["order_id"]
        old = self._seen.get(order_id)
        self._seen[order_id] = (state["step"], list(state["notes"]))
        if old is None:
            return
        for event, count, detail, info in history.changes(old[0], old[1], state["step"],
                                                          state["notes"]):
            self.record(order_id, event, state=state, count=count, detail=detail,
                        info=info or None)

    def _record_sizes(self, state):
        """The photos stopped arriving: how many came with and without HD."""
        with self._saved:
            sizes = list(self._sizes.get(state["order_id"], {}).values())
        self.record(state["order_id"], "photos_arrived", state=state, count=state["photos"],
                    info={"sizes_known": sum(1 for s in sizes if s),
                          "without_hd": sum(s == WITHOUT_HD_PIXELS for s in sizes),
                          "with_hd": sum(bool(s) and s > WITHOUT_HD_PIXELS for s in sizes),
                          "smaller": sum(bool(s) and s < WITHOUT_HD_PIXELS for s in sizes)})

    def _load(self, phone):
        if phone not in self._states:
            row = self.db.latest_order(phone)
            if row and row["status"] != "cancelled":
                self._states[phone] = {
                    "order_id": row["id"], "step": row["step"], "design": row["design"],
                    "photos": row["photo_count"], "title": row["title"],
                    "notes": list(row["notes"] or []),
                }
                if row.get("price") is not None:
                    self._states[phone]["price"] = row["price"]
                ship = {f: row["ship_" + f] for f in conversation.SHIP_FIELDS
                        if row.get("ship_" + f)}
                if ship:
                    self._states[phone]["ship"] = ship
                self._seen[row["id"]] = (row["step"], list(self._states[phone]["notes"]))
                if self.history:
                    self.history.know(row["id"], phone)
                if "done_waiting" in self._states[phone]["notes"]:
                    # The bot restarted while waiting for the last photos: don't wait again.
                    self._states[phone]["notes"].remove("done_waiting")
            else:
                state = conversation.new_state()
                state["order_id"] = self._new_order(phone, state)
                if row and "expired" in (row["notes"] or []) and row.get("photo_count"):
                    state["expired_before"] = True   # said once, at their next message
                self._states[phone] = state
        return self._states[phone]

    def reload_after(self, phone, order_id, change):
        """Task 3.4 (cleanup.py): forget the customer's remembered state of
        this order, then change(); the next message reads it from Supabase."""
        with self.lock_for(phone):
            state = self._states.get(phone)
            if state and state["order_id"] == order_id:
                del self._states[phone]
            self._seen.pop(order_id, None)
            self._sizes.pop(order_id, None)
            change()

    def _albums_today(self, phone):
        """How many albums this phone number started today (Israel's day, as
        set on the Mac). 0 if Supabase can't tell: never block on an error."""
        midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0,
                                                       microsecond=0)
        try:
            return self.db.orders_since(phone, midnight.isoformat())
        except (DatabaseError, AttributeError) as error:
            log.warning("Could not count today's albums: %s", error)
            return 0

    def _new_order(self, phone, state):
        order_id = self.db.create_order(phone, _fields(state))["id"]
        log.info("New order %s", short(order_id))
        self._seen[order_id] = (state["step"], list(state["notes"]))
        self.record(order_id, "order_started", state=state, phone=phone)
        source = self._sources.get(phone)
        if source and time.monotonic() - source[2] < SOURCE_CARRY_SECONDS:
            # They came from an ad or link and then started (another) album.
            self.record(order_id, "source", state=state, detail=source[0],
                        info=dict(source[1] or {}, carried=True))
        return order_id

    def _cancel(self, order_id):
        self._sizes.pop(order_id, None)
        try:
            self.db.update_order(order_id, {"status": "cancelled"})
        except DatabaseError as error:
            log.error("Could not cancel order %s: %s", short(order_id), error)
            return
        log.info("Order %s cancelled (customer started a new album)", short(order_id))
        self._seen.pop(order_id, None)
        timer = threading.Timer(DELETE_DELAY_SECONDS, self._delete_photos, args=(order_id,))
        timer.daemon = True
        timer.start()

    def _delete_photos(self, order_id):
        try:
            count = self.db.delete_order_photos(order_id)
            log.info("Deleted %s photos of cancelled order %s", count, short(order_id))
        except DatabaseError as error:
            log.error("Could not delete photos of order %s: %s", short(order_id), error)


def _snapshot(state):
    """What a message could change, to tell whether it changed anything."""
    return (state["order_id"], state["step"], tuple(state["notes"]), state["photos"],
            state["title"], state["design"], tuple(sorted((state.get("ship") or {}).items())))


def _token(state):
    for note in state["notes"]:
        if note.startswith("owner_token:"):
            return note.split(":", 1)[1]
    return None


def _status(step):
    if step == "paid":
        return "paid"
    if step in conversation.AFTER_APPROVAL:
        return "approved"   # the owner approved it: address and payment
    return "ready" if step == "done" else "collecting"


def _fields(state):
    """The order's columns in Supabase, from the conversation state."""
    fields = {
        "step": state["step"],
        "status": _status(state["step"]),
        "design": state["design"],
        "title": state["title"],
        "photo_count": state["photos"],
        "notes": state["notes"],
    }
    # Task 3.2. Only once there is one, so the bot keeps working even before
    # the new columns were added (supabase/3.2-address-and-payment.sql and
    # 3.2b-shipping-fields.sql).
    for field, value in (state.get("ship") or {}).items():
        fields["ship_" + field] = value
    if state.get("price"):
        fields["price"] = state["price"]
    return fields


def save_photo(db, whatsapp, order_id, number, media, attempts=3, wait=5, on_size=None,
               record=None):
    """Download one photo from WhatsApp and save it in Supabase.

    media is {"id": ..., "mime_type": ...} from the WhatsApp message.
    Tries a few times if the internet hiccups. Returns True if saved.
    We never log anything about the photo except its number.
    on_size(long_side) is called once it's saved (None if the size can't be read).
    record(event, count=, detail=, info=) adds a row to the order history (task 3.3):
    "photo_saved" (its size, HD or not, how long saving took) or "photo_failed".
    """
    record = record or (lambda *args, **kwargs: None)
    started = time.monotonic()
    too_big = False
    name = f"photo {number} of order {short(order_id)}"
    mime_type = (media.get("mime_type") or "image/jpeg").split(";")[0].strip().lower()
    path = f"{order_id}/{number:03d}.{FILE_TYPES.get(mime_type, 'jpg')}"

    # Record it first. This also stops the same photo being saved twice
    # (Meta sometimes sends the same message again).
    try:
        row = db.add_photo({"order_id": order_id, "number": number,
                            "wa_media_id": media["id"], "storage_path": path,
                            "mime_type": mime_type, "size_bytes": 0})
    except DatabaseError as error:
        log.error("Could not save %s: %s", name, error)
        record("photo_failed", count=number, detail="database")
        return False
    if row is None:
        log.info("Skipped %s: this photo was already saved", name)
        return True

    for attempt in range(1, attempts + 1):
        try:
            info = whatsapp.photo_info(media["id"])
            size = int(info.get("file_size") or 0)
            if size > MAX_PHOTO_BYTES:
                log.error("Did not save %s: too big (%s MB)", name, size // 1_000_000)
                record("photo_failed", count=number, detail="too_big",
                       info={"kb": size // 1024})
                too_big = True
                break
            data = whatsapp.download(info["url"])
            db.upload(path, data, mime_type)
            db.update_photo_size(row["id"], len(data))
            log.info("Saved %s", name)
            long_side = image_long_side(data)
            if on_size:
                on_size(long_side)
            record("photo_saved", count=number, detail=mime_type.split("/")[-1],
                   info={"kb": len(data) // 1024, "long_side": long_side,
                         "without_hd": long_side == WITHOUT_HD_PIXELS,
                         "tries": attempt, "seconds": round(time.monotonic() - started, 1)})
            return True
        except (WhatsAppError, DatabaseError, KeyError, ValueError) as error:
            log.warning("Try %s/%s to save %s failed: %s", attempt, attempts, name, error)
            if attempt < attempts:
                time.sleep(wait * attempt)

    log.error("❌ Could not save %s. The customer's count includes it.", name)
    if not too_big:
        record("photo_failed", count=number, detail="error", info={"tries": attempts})
    try:
        db.remove_photo_row(row["id"])
    except DatabaseError:
        pass
    return False


def image_long_side(data):
    """The long side of a JPEG or PNG photo in pixels, read from its header
    (built-in Python only, no Pillow). None for other kinds (HEIC, WebP) or
    if it can't be read. WhatsApp sends JPEG, with or without HD."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            width = int.from_bytes(data[16:20], "big")
            height = int.from_bytes(data[20:24], "big")
            return max(width, height) or None
        if data[:2] != b"\xff\xd8":
            return None
        i = 2
        while i + 9 < len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:   # padding
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            length = int.from_bytes(data[i + 2:i + 4], "big")
            # SOF markers (frame header) hold the size; C4, C8, CC are not frames.
            if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
                height = int.from_bytes(data[i + 5:i + 7], "big")
                width = int.from_bytes(data[i + 7:i + 9], "big")
                return max(width, height) or None
            i += 2 + length
    except (IndexError, TypeError):
        pass
    return None
