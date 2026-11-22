"""Customers' orders and photos (task 1.3).

- Each customer's place in the conversation is kept in memory AND saved in
  Supabase after every message, so restarting the bot (or the Mac) no longer
  starts everyone over.
- Every accepted photo is downloaded from WhatsApp and saved in the private
  Supabase bucket, as <order id>/001.jpg, 002.jpg, ... in the order received.
- If a customer starts a new album before finishing the old one, the old one
  is marked "cancelled" and its photos are deleted.

The conversation itself (what to answer) is still in conversation.py.
"""

import logging
import threading
import time

import conversation
from database import DatabaseError
from whatsapp import WhatsAppError

log = logging.getLogger("bot")

# WhatsApp allows up to 100 MB for files; we don't need more than this per photo.
# (Must stay at or below the bucket's 50 MB limit.)
MAX_PHOTO_BYTES = 40 * 1024 * 1024
FILE_TYPES = {"image/jpeg": "jpg", "image/jpg": "jpg", "image/png": "png",
              "image/heic": "heic", "image/heif": "heif", "image/webp": "webp"}
# Wait a little before deleting a cancelled order's photos, so photos that are
# still uploading get deleted too.
DELETE_DELAY_SECONDS = 60


def short(order_id):
    """The first 8 characters of an order ID: enough to find it in the logs."""
    return (order_id or "?")[:8]


class Orders:
    def __init__(self, db):
        self.db = db
        self._states = {}   # phone -> conversation state
        self._locks = {}    # phone -> lock (one message at a time per customer)
        self._guard = threading.Lock()

    def lock_for(self, phone):
        with self._guard:
            return self._locks.setdefault(phone, threading.Lock())

    def answer(self, phone, kind, value, texts):
        """Answer one message. Call it while holding lock_for(phone).

        Returns (replies, photo) where photo is None, or (order_id, number) when
        this message is a photo that should be saved.
        Raises DatabaseError only if Supabase can't be reached to find or create
        the customer's order (then nothing has changed).
        """
        state = self._load(phone)
        old_order, old_step = state["order_id"], state["step"]
        count_before = state["photos"]

        replies = conversation.answer(state, kind, value, texts)

        if "order_id" not in state:
            # "אלבום חדש": answer() started a fresh state, so open a new order.
            try:
                state["order_id"] = self._new_order(phone, state)
            except DatabaseError:
                del self._states[phone]  # reload from Supabase next time
                raise
            if old_step != "done":
                self._cancel(old_order)
            return replies, None
        try:
            self.db.update_order(state["order_id"], _fields(state))
        except DatabaseError as error:
            # The bot still remembers it; the next message saves it again.
            log.error("Could not save order %s: %s", short(state["order_id"]), error)

        photo = None
        if kind == "photo" and state["photos"] > count_before:
            photo = (state["order_id"], state["photos"])
        return replies, photo

    def _load(self, phone):
        if phone not in self._states:
            row = self.db.latest_order(phone)
            if row and row["status"] != "cancelled":
                self._states[phone] = {
                    "order_id": row["id"], "step": row["step"], "design": row["design"],
                    "photos": row["photo_count"], "title": row["title"],
                    "notes": list(row["notes"] or []),
                }
            else:
                state = conversation.new_state()
                state["order_id"] = self._new_order(phone, state)
                self._states[phone] = state
        return self._states[phone]

    def _new_order(self, phone, state):
        order_id = self.db.create_order(phone, _fields(state))["id"]
        log.info("New order %s", short(order_id))
        return order_id

    def _cancel(self, order_id):
        try:
            self.db.update_order(order_id, {"status": "cancelled"})
        except DatabaseError as error:
            log.error("Could not cancel order %s: %s", short(order_id), error)
            return
        log.info("Order %s cancelled (customer started a new album)", short(order_id))
        timer = threading.Timer(DELETE_DELAY_SECONDS, self._delete_photos, args=(order_id,))
        timer.daemon = True
        timer.start()

    def _delete_photos(self, order_id):
        try:
            count = self.db.delete_order_photos(order_id)
            log.info("Deleted %s photos of cancelled order %s", count, short(order_id))
        except DatabaseError as error:
            log.error("Could not delete photos of order %s: %s", short(order_id), error)


def _fields(state):
    """The order's columns in Supabase, from the conversation state."""
    return {
        "step": state["step"],
        "status": "ready" if state["step"] == "done" else "collecting",
        "design": state["design"],
        "title": state["title"],
        "photo_count": state["photos"],
        "notes": state["notes"],
    }


def save_photo(db, whatsapp, order_id, number, media, attempts=3, wait=5):
    """Download one photo from WhatsApp and save it in Supabase.

    media is {"id": ..., "mime_type": ...} from the WhatsApp message.
    Tries a few times if the internet hiccups. Returns True if saved.
    We never log anything about the photo except its number.
    """
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
                break
            data = whatsapp.download(info["url"])
            db.upload(path, data, mime_type)
            db.update_photo_size(row["id"], len(data))
            log.info("Saved %s", name)
            return True
        except (WhatsAppError, DatabaseError, KeyError, ValueError) as error:
            log.warning("Try %s/%s to save %s failed: %s", attempt, attempts, name, error)
            if attempt < attempts:
                time.sleep(wait * attempt)

    log.error("❌ Could not save %s. The customer's count includes it.", name)
    try:
        db.remove_photo_row(row["id"])
    except DatabaseError:
        pass
    return False
