"""Check the customer's cover photo as soon as it arrives (task 2.5).

Why: the owner's first cover printed at only 146 DPI (a wide photo, sent
without HD, cut to the square cover). Now the customer hears about it within
seconds, while they still have their phone in hand:

1. The cover photo arrives: the conversation answers at once "got it, checking…"
   (step "cover_check"), and orders.py calls CoverChecks.start().
2. In the background, this waits for that one photo to be saved in Supabase,
   then runs album/check_cover.py on it (with the .venv Python, like the album).
3. The answer goes to conversation.cover_checked(): good -> the usual "beautiful
   photo" message; too small or blurry -> buttons [send another] [continue].

If the check can't run (album tools missing, Supabase down), the photo is
accepted: the album itself shows a too-small cover smaller, and the owner
approves every album anyway.
"""

import json
import logging
import subprocess
import threading

from orders import short
from settings import PROJECT_DIR

log = logging.getLogger("bot")

ALBUM_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
CHECK_SCRIPT = PROJECT_DIR / "album" / "check_cover.py"
PHOTO_WAIT_SECONDS = 120
TOOL_SECONDS = 120


class CoverChecks:
    def __init__(self, orders, send, texts, run_tool=None):
        self.orders = orders
        self.send = send          # send(phone, message) -> True if sent
        self.texts = texts
        self.run_tool = run_tool or run_check_tool

    def start(self, phone, order_id, number):
        """Check in the background (called by orders.py)."""
        threading.Thread(target=self._safe_run, args=(phone, order_id, number),
                         daemon=True).start()

    def _safe_run(self, phone, order_id, number):
        try:
            self.run(phone, order_id, number)
        except Exception:
            log.exception("Something went wrong while checking cover photo of %s",
                          short(order_id))

    def run(self, phone, order_id, number):
        name = short(order_id)
        result = None
        if not self.orders.wait_for_photos(order_id, PHOTO_WAIT_SECONDS, number):
            log.warning("Cover photo of %s took too long to save; not checked", name)
        else:
            result = self.run_tool(order_id, number)
        if result:
            log.info("Cover photo %s of %s: %s (%s DPI on the cover)", number, name,
                     "ok" if result["ok"] else result["problem"], result["dpi"])
        replies = self.orders.cover_checked(phone, order_id, number, result, self.texts)
        for reply in replies:
            self.send(phone, reply)


def run_check_tool(order_id, number):
    """Run album/check_cover.py on one photo of an order. Returns its result, or None."""
    if not ALBUM_PYTHON.exists():
        log.error("❌ Album tools not installed (%s is missing): cover photo not checked. "
                  "See docs/setup/2.1-quality-check.md, step 1.", ALBUM_PYTHON)
        return None
    command = [str(ALBUM_PYTHON), str(CHECK_SCRIPT), "--order", order_id,
               "--photo", str(number), "--json"]
    try:
        done = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True,
                              text=True, timeout=TOOL_SECONDS)
    except subprocess.TimeoutExpired:
        log.error("❌ Cover check of %s took too long", short(order_id))
        return None
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines:
        log.error("❌ Cover check of %s failed: %s", short(order_id),
                  (done.stderr or done.stdout).strip()[-800:])
        return None
    try:
        return json.loads(lines[-1])
    except ValueError:
        return None
