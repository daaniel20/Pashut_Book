"""Build the album when an order is complete (task 2.2).

When a customer finishes (design, photos, cover title), the bot calls
AlbumJobs.start(). In the background it:
1. waits until all the order's photos are saved in Supabase,
2. checks the photos (album/build_album.py --check),
3. if most photos came WITHOUT HD, asks the customer whether to resend them
   in HD (buttons: [How do I send HD?] [Continue anyway]), and stops there.
   When they tap "Continue anyway", the order is complete again and this runs again.
4. otherwise, tells the customer in one short message if photos were left out
   (blurry, duplicates), and builds the album.

If the customer changes the title or design from the summary while the album
is being built, it is built again when the current build ends.

5. (task 2.4) sends the customer ONE message with the cover picture and a
   button that opens a private web page with the whole album (small images with
   a PREVIEW mark, two pages per image, numbered; see preview_links.py), then a
   message with buttons [Love it] [Change something].
   They are not sent if the customer is in the middle of changing something:
   the album is built again when they finish, and the new previews are sent.

The album is built on this Mac, in output/albums/<order>/ (open album.html;
the customer's images are in its preview/ folder). The owner's approval before
printing is task 3.1.

The album tools need Pillow, so they run with the project's .venv Python, as a
separate program. The bot itself still uses only Python's built-in tools.
"""

import json
import logging
import subprocess
import threading
import time

import conversation
from orders import short
from settings import PROJECT_DIR

log = logging.getLogger("bot")

ALBUM_PYTHON = PROJECT_DIR / ".venv" / "bin" / "python"
BUILD_SCRIPT = PROJECT_DIR / "album" / "build_album.py"
# Ask to resend in HD when at least this part of the photos came without it.
WITHOUT_HD_SHARE = 0.5
PHOTOS_WAIT_SECONDS = 15 * 60
TOOL_SECONDS = 20 * 60


class AlbumJobs:
    def __init__(self, orders, send, texts, run_tool=None, make_link=None):
        self.orders = orders
        self.send = send              # send(phone, message) -> True if sent
        # make_link(result) -> the web address of the album's preview page
        self.make_link = make_link
        self.texts = texts
        self.run_tool = run_tool or run_album_tool
        self._running = set()
        self._again = set()   # changed while building: build once more
        self._told = set()    # already told which photos were left out
        self._guard = threading.Lock()

    def start(self, phone, order_id):
        """Check and build in the background (called by orders.py)."""
        with self._guard:
            if order_id in self._running:
                self._again.add(order_id)
                return
            self._running.add(order_id)
        threading.Thread(target=self._safe_run, args=(phone, order_id), daemon=True).start()

    def _safe_run(self, phone, order_id):
        while True:
            try:
                self.run(phone, order_id)
            except Exception:
                log.exception("Something went wrong while building album %s", short(order_id))
            with self._guard:
                if order_id in self._again:
                    self._again.discard(order_id)
                    log.info("Album %s: the customer changed something; building again",
                             short(order_id))
                    continue
                self._running.discard(order_id)
                return

    def run(self, phone, order_id):
        name = short(order_id)
        if not self.orders.wait_for_photos(order_id, PHOTOS_WAIT_SECONDS):
            log.warning("Album %s: some photos are still saving; checking anyway", name)

        started = time.monotonic()
        info = self.run_tool(order_id, check_only=True)
        if not info:
            self._record(phone, order_id, "album_check_failed")
            return
        notes = self.orders.notes_of(phone, order_id)
        if notes is None:
            log.info("Album %s: the customer started another order; stopped", name)
            return
        log.info("Album %s: %s photos, %s without HD, left out %s", name,
                 info["photos"], info["without_hd"], info["left_out"])
        self._record(phone, order_id, "album_checked", count=info["photos"],
                     info=dict(_numbers(info), seconds=_since(started)))

        if needs_hd(info) and "hd_asked" not in notes:
            if self.orders.ask_hd(phone, order_id):
                self.send(phone, conversation.hd_question(self.texts))
                log.info("Album %s: asked the customer to resend in HD", name)
            return

        message = conversation.left_out_message(info["left_out"], self.texts)
        if message and order_id not in self._told:
            self._told.add(order_id)
            self.send(phone, {"text": message})

        started = time.monotonic()
        result = self.run_tool(order_id, check_only=False)
        if result and "pages" in result:
            log.info("✅ Album %s built: %s pages. Open %s/album.html",
                     name, result["pages"], result["folder"])
            self._record(phone, order_id, "album_built", count=result["pages"],
                         detail=result.get("design"),
                         info=dict(_numbers(result), seconds=_since(started)))
            self.send_previews(phone, order_id, result)
        else:
            if result:
                log.error("❌ Album %s was not built: %s", name, result.get("error"))
            self._record(phone, order_id, "album_failed", info={"seconds": _since(started)})

    def _record(self, phone, order_id, event, **values):
        """A moment in the order history (task 3.3)."""
        record = getattr(self.orders, "record_for", None)
        if record:
            record(phone, order_id, event, **values)

    def send_previews(self, phone, order_id, result):
        """Send the customer the link to the album's preview (task 2.4)."""
        name = short(order_id)
        with self._guard:
            if order_id in self._again:
                return   # it changed while building: the new album's previews come next
        if not self.orders.is_done(phone, order_id):
            log.info("Album %s: the customer is changing something; previews wait", name)
            self._record(phone, order_id, "previews_waiting")
            return
        previews = result.get("previews") or []
        if not previews or not self.make_link:
            log.warning("Album %s: no preview images to send (is the album tool up to date? "
                        "run git pull)", name)
            return
        t = self.texts
        result["order_id"] = order_id   # the page's visits are recorded (task 3.3b)
        url = self.make_link(result)
        message = {"text": t["preview_intro"].format(pages=result["pages"]),
                   "link": {"button": t["button_preview_link"], "url": url},
                   "image_file": previews[0]["file"]}   # the cover on top
        if not self.send(phone, message):
            log.error("❌ Album %s: the preview link was not sent", name)
            self._record(phone, order_id, "previews_not_sent")
            return
        self.send(phone, conversation.after_previews(t))
        self.orders.add_note(phone, order_id, "previews_sent")
        log.info("Album %s: sent the preview link", name)


def album_numbers(order_id):
    """The numbers of the photos inside the album as last built (not the cover),
    from its layout.json (task 3.2). None if it can't be read."""
    path = PROJECT_DIR / "output" / "albums" / short(order_id) / "layout.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        names = [spot["photo"] for page in data["pages"] for spot in page["spots"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    numbers = set()
    for name in names:
        if isinstance(name, str) and name.startswith("photo ") and name[6:].isdigit():
            numbers.add(int(name[6:]))
    return numbers


def album_removable(order_id):
    """The numbers of the photos the customer may remove (task 3.2): a photo
    that shares its page always; a photo alone on its page only if the album
    stays at least its minimum length without that page. None if unknown."""
    path = PROJECT_DIR / "output" / "albums" / short(order_id) / "layout.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pages = [[spot["photo"] for spot in page["spots"]] for page in data["pages"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    content = [names for names in pages if names]
    shorter = len(content) - 1 + (len(content) - 1) % 2   # without one page, kept even
    page_may_go = shorter >= data.get("min_pages", 20)
    removable = set()
    for names in content:
        if len(names) > 1 or page_may_go:
            removable.update(int(n[6:]) for n in names
                             if isinstance(n, str) and n.startswith("photo ") and n[6:].isdigit())
    return removable


def _since(started):
    return round(time.monotonic() - started, 1)


def _numbers(result):
    """The album tool's numbers for the order history (task 3.3): no names, no texts."""
    numbers = {key: result[key] for key in
               ("photos", "used", "without_hd", "pages", "photos_in_album",
                "photos_on_pages", "full_pages") if isinstance(result.get(key), int)}
    for reason, count in (result.get("left_out") or {}).items():
        numbers["left_out_" + reason] = count
    if isinstance(result.get("notes"), list):
        numbers["owner_notes"] = len(result["notes"])
    return numbers


def needs_hd(info):
    return info["photos"] > 0 and info["without_hd"] >= WITHOUT_HD_SHARE * info["photos"]


def run_album_tool(order_id, check_only):
    """Run album/build_album.py for an order. Returns its result, or None."""
    if not ALBUM_PYTHON.exists():
        log.error("❌ Album tools not installed (%s is missing). "
                  "See docs/setup/2.1-quality-check.md, step 1.", ALBUM_PYTHON)
        return None
    command = [str(ALBUM_PYTHON), str(BUILD_SCRIPT), "--order", order_id, "--json"]
    if check_only:
        command.append("--check")
    try:
        done = subprocess.run(command, cwd=PROJECT_DIR, capture_output=True,
                              text=True, timeout=TOOL_SECONDS)
    except subprocess.TimeoutExpired:
        log.error("❌ Album %s: the album tool took too long", short(order_id))
        return None
    lines = done.stdout.strip().splitlines()
    if done.returncode != 0 or not lines:
        log.error("❌ Album %s: the album tool failed: %s", short(order_id),
                  (done.stderr or done.stdout).strip()[-800:])
        return None
    return json.loads(lines[-1])
