"""Behaviour data (task 3.3b): how customers use the bot, in numbers and codes.

The owner wants to understand how customers behave, find where they get stuck,
and later build a dashboard (CLAUDE.md rule 10). Task 3.3 records every step of
every order; this file adds the rest, all written as rows of the same order
history (history.py, table "order_events"):

- where the customer came from: a source code in our wa.me links (read_source),
  or the ad details Meta attaches to a click on a "click to WhatsApp" ad;
- a test mark: orders from the owner's and family phones (TEST_PHONES in .env);
- every incoming message: its kind, the button tapped, whether it changed
  anything, the text's LENGTH only (never the text);
- delivered / read for each bot message, with the message's name (e.g.
  "photos_count"), found by matching the text against the texts file;
- the album page: opened, from how many devices, phone or computer, how far
  they scrolled (the page sends a tiny note back, preview_links.py);
- the bot's version on every row (the code's date + git commit);
- a permanent anonymous customer key on every row: the phone number scrambled
  with a secret (HMAC). The same phone always gets the same key, but the key
  can't be turned back into the number. So repeat customers can be counted
  even after old orders are cleaned up (task 3.4).

Never recorded: photos, message texts, names, addresses, phone numbers.
Built-in Python only.
"""

import hashlib
import hmac
import re
import secrets
import subprocess
import threading
import time
from collections import OrderedDict

from settings import ENV_FILE, PROJECT_DIR

# ---------- the anonymous customer key ----------

KEY_SECRET_NAME = "CUSTOMER_KEY_SECRET"
KEY_LETTERS = 16


def customer_key(phone, secret):
    """The phone number scrambled with our secret: 16 letters and digits.
    The same number always gives the same key; the key can't be turned back."""
    if not phone or not secret:
        return None
    digits = "".join(c for c in str(phone) if c.isdigit())
    return hmac.new(secret.encode("utf-8"), digits.encode("utf-8"),
                    hashlib.sha256).hexdigest()[:KEY_LETTERS]


def key_secret(env, env_file=ENV_FILE):
    """The secret for customer keys, from .env. The first time, a new random
    one is made and added to .env by itself. It must never change (then the
    same customer would get a new key), so keep a copy (guide 3.3b)."""
    secret = env.get(KEY_SECRET_NAME)
    if secret:
        return secret
    secret = secrets.token_hex(32)
    try:
        with open(env_file, "a", encoding="utf-8") as file:
            file.write("\n# Task 3.3b: scrambles phone numbers into anonymous customer keys.\n"
                       "# Made by the bot. NEVER change or delete it; keep a copy (guide 3.3b).\n"
                       f"{KEY_SECRET_NAME}={secret}\n")
    except OSError:
        return None   # no key this time, rather than a key that changes on every start
    env[KEY_SECRET_NAME] = secret
    return secret


# ---------- the test mark ----------

def phone_number(value):
    """A phone number as WhatsApp writes it (972…, digits only)."""
    digits = "".join(c for c in value or "" if c.isdigit())
    if digits.startswith("0"):
        digits = "972" + digits[1:]
    return digits or None


def test_phones(env):
    """The owner's phone and the family's test phones (TEST_PHONES in .env,
    separated by commas). Their orders are marked as tests."""
    values = [env.get("OWNER_PHONE") or ""] + (env.get("TEST_PHONES") or "").split(",")
    return {number for number in (phone_number(v) for v in values) if number}


# ---------- the bot's version ----------

def bot_version(folder=PROJECT_DIR):
    """The code's version: "2026-11-26.e83a816" (the date of the last change,
    then its git commit), so rows can be compared before and after a change.
    "unknown" if git can't tell."""
    try:
        # (safe.directory: the bot's service may run as another user than the
        # folder's owner, and git would refuse to read it.)
        out = subprocess.run(["git", "-c", "safe.directory=*", "log", "-1",
                              "--format=%cs.%h"], cwd=folder,
                             capture_output=True, text=True, timeout=10)
        version = out.stdout.strip()
        if out.returncode == 0 and version:
            return version
    except (OSError, subprocess.SubprocessError):
        pass
    return _commit_from_files(folder) or "unknown"


def _commit_from_files(folder):
    """The current commit (first 7 characters), read from the .git folder
    directly, for when the git command can't run."""
    git = folder / ".git"
    try:
        head = (git / "HEAD").read_text().strip()
        if not head.startswith("ref: "):
            return head[:7]
        ref = head[5:]
        path = git / ref
        if path.exists():
            return path.read_text().strip()[:7]
        for line in (git / "packed-refs").read_text().splitlines():
            if line.endswith(" " + ref):
                return line[:7]
    except OSError:
        pass
    return None


# ---------- where the customer came from ----------

# A source code in the ready-made first message of our wa.me links, e.g.
# "שלום, אשמח לאלבום #101". Either a number of 3-6 digits (owner's choice, Nov 26,
# 2026: the first digit is the channel, e.g. 1xx Facebook, 2xx WhatsApp groups),
# or letters that start with a letter ("#fb1"). So "#1" in a title isn't a code.
_SOURCE = re.compile(r"#(\d{3,6}|[A-Za-z][A-Za-z0-9_-]{1,19})\b")
CODE = re.compile(r"\d{3,6}|[a-z][a-z0-9_-]{1,19}")


def read_source(message):
    """(code, details) of where this message came from, or (None, None).
    code: from "#code" in a text, or "ad" / "post" for a click on a Meta
    "click to WhatsApp" ad (Meta attaches "referral" to that first message).
    details: the ad's ID and kind (never the customer's details)."""
    code, details = None, None
    if message.get("type") == "text":
        found = _SOURCE.search(message.get("text", {}).get("body", ""))
        if found:
            code = found.group(1).lower()
    referral = message.get("referral")
    if isinstance(referral, dict):
        details = {key: str(referral[name])[:40] for key, name in
                   (("type", "source_type"), ("ad_id", "source_id"), ("media", "media_type"))
                   if referral.get(name)}
        details["from_ad"] = True
        code = code or details.get("type") or "ad"
    return code, details


# ---------- which message is it? ----------

_names_cache = {}


def _patterns(texts):
    key = id(texts)
    if key not in _names_cache:
        patterns = []
        for name, text in texts.items():
            if not isinstance(text, str) or name.startswith("button_") or \
                    name.endswith("_words"):
                continue
            parts = re.split(r"\{[^{}]*\}", text)
            regex = "(?s)" + ".*?".join(re.escape(p) for p in parts)
            literal = sum(len(p.strip()) for p in parts)
            if literal < 6:
                continue   # too little fixed text to recognise it by
            patterns.append((literal, name, re.compile(regex)))
        patterns.sort(key=lambda p: -p[0])   # the most specific text first
        _names_cache[key] = (texts, patterns)
    return _names_cache[key][1]


def message_name(message, texts):
    """The name of a bot message in the texts file ("photos_count", "welcome"…),
    found by matching its text. "other" if it isn't from the texts file."""
    text = message.get("text") or message.get("caption") or ""
    if not text:
        return "image" if message.get("image_file") else "other"
    patterns = _patterns(texts)
    for _, name, regex in patterns:          # the whole message is this text
        if regex.fullmatch(text):
            return name
    for _, name, regex in patterns:          # or it starts with it (more was added)
        if regex.match(text):
            return name
    for _, name, regex in patterns:          # or it holds it ("✅ saved…" + the question)
        if regex.search(text):
            return name
    return "other"


def message_kind(message):
    """What the bot sent: text, buttons, list, link, video or image."""
    for kind, field in (("video", "video_file"), ("link", "link"), ("list", "list"),
                        ("buttons", "buttons"), ("image", "image_file")):
        if message.get(field):
            return kind
    return "text"


# ---------- what the customer was expected to send ----------

TEXT_STEPS = ("title", "photo_number", "ship_name", "ship_street", "ship_city", "ship_phone")
PHOTO_STEPS = ("cover_photo", "photos", "photo_replace")


def expected(step, notes=()):
    """What the bot waited for at this step: "text", "photo", "button" or "any"."""
    if "help_wait" in notes or step in TEXT_STEPS:
        return "text"
    if step in PHOTO_STEPS:
        return "photo"
    if step in (None, "new"):
        return "any"
    return "button"


def button_code(value):
    """A tapped button's ID without anything after ":" (owner buttons carry an
    order ID and a code)."""
    return (value or "").split(":", 1)[0][:40]


# ---------- sent messages, until WhatsApp says delivered / read ----------

class Outbox:
    """Remembers the bot's recent messages to customers (WhatsApp's message ID
    -> order, message name, when sent), so "delivered" and "read" reports can be
    recorded with the message's name. In memory only: reports for messages sent
    before a restart are skipped."""

    def __init__(self, size=5000):
        self._sent = OrderedDict()
        self._size = size
        self._lock = threading.Lock()

    def add(self, message_id, phone, order_id, name):
        if not message_id:
            return
        with self._lock:
            self._sent[message_id] = {"phone": phone, "order_id": order_id, "name": name,
                                      "sent": time.time(), "seen": set()}
            while len(self._sent) > self._size:
                self._sent.popitem(last=False)

    def report(self, message_id, status, timestamp=None):
        """A delivery report: the sent message's details plus "seconds" (from
        sending to this report), or None if unknown or already reported."""
        with self._lock:
            sent = self._sent.get(message_id)
            if not sent or status in sent["seen"]:
                return None
            sent["seen"].add(status)
        try:
            when = float(timestamp)
        except (TypeError, ValueError):
            when = time.time()
        return dict(sent, seconds=max(0, round(when - sent["sent"])))


# ---------- the album page ----------

_DEVICE = re.compile(r"^[a-z0-9]{8,16}$")
PAGE_NOTES_PER_HOUR = 60   # per link: a limit, so nobody can flood the history


def device_kind(user_agent):
    """"phone", "tablet" or "computer", from the browser's description."""
    agent = (user_agent or "").lower()
    if "ipad" in agent or ("android" in agent and "mobile" not in agent):
        return "tablet"
    if any(word in agent for word in ("iphone", "android", "mobile")):
        return "phone"
    return "computer"


class PageNotes:
    """Checks the small notes the album page sends ("opened", "how far they
    scrolled") and limits them per link."""

    def __init__(self, per_hour=PAGE_NOTES_PER_HOUR):
        self.per_hour = per_hour
        self._counts = {}
        self._lock = threading.Lock()

    def allowed(self, code):
        hour = int(time.time() // 3600)
        with self._lock:
            if len(self._counts) > 10000:
                self._counts.clear()
            count = self._counts.get((code, hour), 0)
            if count >= self.per_hour:
                return False
            self._counts[(code, hour)] = count + 1
            return True

    @staticmethod
    def read(data, user_agent):
        """(event, count, detail, info) from the page's note, or None if it
        isn't a valid note. Only small numbers and a random device code."""
        if not isinstance(data, dict):
            return None
        device = str(data.get("d") or "")
        if not _DEVICE.match(device):
            return None
        detail = "owner" if data.get("o") else device_kind(user_agent)

        def number(name, top):
            try:
                return max(0, min(top, int(data.get(name) or 0)))
            except (TypeError, ValueError):
                return 0
        if data.get("e") == "open":
            return "album_opened", None, detail, {"device": device}
        if data.get("e") == "seen":
            return "album_seen", number("depth", 100), detail, {
                "device": device, "seconds": number("seconds", 24 * 3600),
                "images_seen": number("images_seen", 500), "images": number("images", 500)}
        return None
