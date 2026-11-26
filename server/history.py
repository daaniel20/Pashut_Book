"""Order history (task 3.3): one row in Supabase for every moment of every order.

Why: the owner wants to study the data later and improve the process
(CLAUDE.md rule 10). Every row says WHAT happened to WHICH order and WHEN,
with numbers only (counts, sizes, choices, seconds). Never photos, never
message texts, never phone numbers (the order's row in "orders" has those).

The rows go to the table "order_events" (supabase/3.3-order-history.sql).
The view "order_history" shows them with the time since the order started
and since the previous row; "order_summary" has one row per order. Download
either as a CSV from Supabase (docs/setup/3.3-order-history.md).

Writing happens in the background, one row after another, so the customer
never waits for it, and a Supabase problem never stops the bot: the row is
tried a few times, then dropped with a line in bot.log.

Task 3.3b: every row also gets the customer's anonymous key ("customer", the
phone number scrambled, behaviour.py), a test mark ("test": the owner's and
family phones) and the bot's version. The order's phone number is learned
from record(..., phone=) or know(), or read from Supabase once.
"""

import logging
import queue
import threading
import time
from datetime import datetime, timezone

import behaviour
from database import DatabaseError

log = logging.getLogger("bot")

TRIES = 3
RETRY_SECONDS = 5
# Notes (orders.py / conversation.py) that are NOT worth a row: codes, dates
# and helper marks that say nothing about the customer's journey.
SKIP_NOTES = {"owner_token", "help_day", "photos_at", "editing", "owner_check"}


# The columns added in task 3.3b (supabase/3.3b-behaviour-data.sql).
NEW_COLUMNS = ("customer", "test", "version")


class History:
    def __init__(self, db, background=True, key_secret=None, test_phones=(), version=None):
        self.db = db
        self.background = background
        self.key_secret = key_secret       # for the anonymous customer key (3.3b)
        self.test_phones = set(test_phones)
        self.version = version
        self._who = {}       # order_id -> (customer key, test?)
        self._who_lock = threading.Lock()
        self._queue = queue.Queue()
        self._warned = False
        self._old_table = False   # the 3.3b columns aren't in Supabase yet
        if background:
            threading.Thread(target=self._worker, daemon=True).start()

    def know(self, order_id, phone):
        """Remember whose order this is (as a key and a test mark, never the number)."""
        if not order_id or not phone:
            return
        who = (behaviour.customer_key(phone, self.key_secret),
               behaviour.phone_number(phone) in self.test_phones)
        with self._who_lock:
            self._who[order_id] = who

    def _whose(self, order_id):
        with self._who_lock:
            who = self._who.get(order_id)
        if who is None:
            # Not seen since the bot started: ask Supabase once (in the background).
            try:
                row = self.db.get_order(order_id)
            except Exception:
                row = None
            if row and row.get("phone"):
                self.know(order_id, row["phone"])
                with self._who_lock:
                    who = self._who.get(order_id)
            else:
                with self._who_lock:
                    who = self._who.setdefault(order_id, (None, None))
        return who

    def record(self, order_id, event, step=None, photos=None, count=None,
               detail=None, info=None, phone=None):
        """Remember one moment of an order. Returns at once.

        event:  what happened, e.g. "step", "album_built", "photo_saved"
        step:   the conversation step at that moment
        photos: how many photos the order had then
        count:  the event's main number (a photo number, pages, …)
        detail: a short code (e.g. the new step, "small"), never customer text
        info:   more numbers, e.g. {"pages": 24, "seconds": 41}
        phone:  the customer's number, if known (only its scrambled key is kept)
        """
        if not order_id or not event:
            return
        if phone:
            self.know(order_id, phone)
        row = {"order_id": order_id, "event": event, "step": step, "photos": photos,
               "count": count, "detail": None if detail is None else str(detail)[:60],
               "info": info or {},
               "created_at": datetime.now(timezone.utc).isoformat(),
               "version": self.version}
        if self.background:
            self._queue.put(row)
        else:
            self._write(row)

    def wait(self, timeout=5):
        """Wait until every row so far is written (for tests and shutting down)."""
        end = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < end:
            time.sleep(0.01)

    def _worker(self):
        while True:
            row = self._queue.get()
            try:
                self._write(row)
            finally:
                self._queue.task_done()

    def _write(self, row):
        if "customer" not in row:
            row["customer"], row["test"] = self._whose(row["order_id"])
        for attempt in range(1, TRIES + 1):
            try:
                if self._old_table:
                    self.db.add_event({k: v for k, v in row.items() if k not in NEW_COLUMNS})
                else:
                    self.db.add_event(row)
                return
            except DatabaseError as error:
                if not self._old_table and "column" in str(error) and \
                        any(name in str(error) for name in NEW_COLUMNS):
                    # supabase/3.3b-behaviour-data.sql wasn't run yet: keep
                    # recording without the new columns, and say so once.
                    self._old_table = True
                    log.warning("Order history: the 3.3b columns are missing (%s). Run "
                                "supabase/3.3b-behaviour-data.sql (docs/setup/"
                                "3.3b-behaviour-data.md). Saving without them for now.", error)
                    continue
                if "order_events" in str(error):
                    # Supabase refused it, most likely because the table doesn't
                    # exist yet. Trying again won't help; say so once.
                    if not self._warned:
                        self._warned = True
                        log.warning("Order history not saved: %s. Did you run "
                                    "supabase/3.3-order-history.sql? "
                                    "(docs/setup/3.3-order-history.md)", error)
                    return
                if attempt == TRIES:
                    log.warning("Order history row %r of %s not saved: %s",
                                row["event"], row["order_id"][:8], error)
                    return
                if self.background:
                    time.sleep(RETRY_SECONDS * attempt)
            except Exception:
                log.exception("Could not save an order history row")
                return


def note_parts(note):
    """A note like "used_title:2" -> ("used_title", 2, None);
    "cover_problem:small" -> ("cover_problem", None, "small")."""
    name, _, value = note.partition(":")
    if value.isdigit():
        return name, int(value), None
    return name, None, value or None


def changes(old_step, old_notes, new_step, new_notes):
    """What happened between two saves of an order: [(event, count, detail, info)].
    A new step is one row; each new note is one row (named after the note)."""
    rows = []
    if new_step != old_step:
        rows.append(("step", None, new_step, {"from": old_step}))
    for note in new_notes:
        if note in old_notes:
            continue
        name, count, detail = note_parts(note)
        if name in SKIP_NOTES:
            continue
        if name == "owner_msgs" and detail:   # "<date>:N": only N is interesting
            last = detail.rsplit(":", 1)[-1]
            count, detail = (int(last), None) if last.isdigit() else (None, None)
        rows.append((name, count, detail, {}))
    return rows
