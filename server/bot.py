"""The Pashut Book WhatsApp bot.

Task 1.1: receive WhatsApp messages and reply.
Task 1.2: the Hebrew conversation with buttons (the steps are in conversation.py).
Task 1.3: save orders and photos in Supabase (orders.py, database.py).
Task 2.2: when an order is complete, check the photos and build the album (album_job.py).
Task 2.4: then send the customer a private link to the album's preview
(album_job.py), and show that page at /album/<code> (preview_links.py).
Task 2.5: check the cover photo as soon as it arrives (cover_check.py).
Task 3.1: when the customer loves the album, ask the owner (OWNER_PHONE in .env)
to approve it, on WhatsApp (owner_approval.py).
Task 3.2: replace or remove a photo by its number, then the shipping address,
and the payment (a Bit request the owner sends by hand).

How it works, in short:
1. A customer writes to our WhatsApp number.
2. Meta sends a "webhook" (an automatic notice) to https://bot.pashutbook.com/webhook.
3. Cloudflare Tunnel passes it to this program on the Mac (port 8000).
4. This program checks the notice really came from Meta, then sends a reply
   through Meta's WhatsApp API.

It uses only Python's built-in tools (nothing to install).
It replaces the old test page (server/hello.py): the page at "/" still works.

Run it by hand:   python3 server/bot.py
Settings come from the private .env file (see .env.example).
"""

import hashlib
import hmac
import json
import logging
import sys
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import conversation
import preview_links
from album_job import AlbumJobs, album_numbers
from cover_check import CoverChecks
from database import Database, DatabaseError
from orders import Orders, save_photo
from owner_approval import OwnerApprovals
from settings import ENV_FILE, PAGES_DIR, load_texts, read_env
from whatsapp import WhatsApp, WhatsAppError

# 127.0.0.1 = "this computer only". Only the Cloudflare Tunnel (on the same Mac)
# can reach it, never other devices on the home Wi-Fi.
HOST = "127.0.0.1"
PORT = 8000
# After a video, wait this long before the next message, so it arrives first.
VIDEO_PAUSE_SECONDS = 2
WEBHOOK_PATH = "/webhook"
# Webhook notices are small. Refuse anything bigger (protects the Mac).
MAX_BODY_BYTES = 1_000_000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger("bot")

REQUIRED = [
    "WHATSAPP_PHONE_NUMBER_ID",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_APP_SECRET",
    "WHATSAPP_VERIFY_TOKEN",
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
]
# How many photos are downloaded and saved at the same time.
PHOTO_WORKERS = 4
# The bot's public address (through the Cloudflare Tunnel), for preview links.
DEFAULT_PUBLIC_URL = "https://bot.pashutbook.com"
# If Supabase is down, tell the customer at most once every 10 minutes.
PROBLEM_NOTICE_SECONDS = 600

env = read_env()
TEXTS = load_texts("he")

# Meta sometimes sends the same message twice. Remember recent message IDs
# so the customer gets one reply, not two.
_seen_ids = deque(maxlen=1000)
_seen_lock = threading.Lock()

# Filled in by main() once the settings are checked.
whatsapp = None
db = None
orders = None
owner = None
photo_savers = ThreadPoolExecutor(max_workers=PHOTO_WORKERS)
_last_problem_notice = {}

PAGE = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pashut Book</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; text-align: center;
         padding: 3em 1em; background: #faf7f2; color: #333; }}
  h1 {{ font-size: 2em; }}
</style>
</head>
<body>
<h1>✅ השרת של פשוט בוק עובד</h1>
<p>הדף הזה מגיע מה-Mac Mini.</p>
<p>{time}</p>
</body>
</html>
"""


def mask_phone(phone):
    """Show only the last 3 digits in logs (phone numbers are private)."""
    return "…" + phone[-3:] if phone else "?"


def is_from_meta(body, signature_header):
    """Check Meta's signature, so strangers can't pretend to be WhatsApp."""
    secret = env["WHATSAPP_APP_SECRET"].encode("utf-8")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header or "")


def is_new_message(message_id):
    with _seen_lock:
        if message_id in _seen_ids:
            return False
        _seen_ids.append(message_id)
        return True


def send(to, message):
    """Send one message. Returns True if Meta accepted it."""
    try:
        whatsapp.send(to, message)
        log.info("%s sent to %s", "Image" if message.get("image_file") else "Reply",
                 mask_phone(to))
        return True
    except (WhatsAppError, OSError) as error:
        log.error("Could not send a message: %s", error)
        return False


def save_photo_safely(order_id, number, media):
    try:
        save_photo(db, whatsapp, order_id, number, media,
                   on_size=lambda side: orders.photo_size(order_id, number, side))
    except Exception:
        log.exception("Something went wrong while saving a photo")
    finally:
        orders.photo_done(order_id, number)   # the album and the cover check wait for this


def handle_notice(data):
    """Read one webhook notice from Meta and answer any new messages in it."""
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # "statuses" = delivery reports (sent / delivered / read / failed).
            for status in value.get("statuses", []):
                if status.get("status") == "failed":
                    report_failed(status)
            for message in value.get("messages", []):
                sender = message.get("from")
                message_id = message.get("id")
                if not sender or not message_id or not is_new_message(message_id):
                    continue
                kind, value = conversation.read_message(message)
                # We log only the message type, never texts or photos.
                log.info("Got a %s message from %s", message.get("type"), mask_phone(sender))
                if owner and owner.handles(sender, kind, value):
                    owner.handle(kind, value)   # the owner's approval (task 3.1)
                    continue
                # Many photos arrive at once, each in its own notice. The lock lets
                # one at a time update this customer's order, so the count is right.
                with orders.lock_for(sender):
                    try:
                        replies, photo = orders.answer(sender, kind, value, TEXTS)
                    except DatabaseError as error:
                        log.error("Supabase problem: %s", error)
                        replies, photo = problem_notice(sender), None
                if photo:
                    order_id, number = photo
                    photo_savers.submit(save_photo_safely, order_id, number, value)
                for number, reply in enumerate(replies):
                    send(sender, reply)
                    if reply.get("video_file") and number < len(replies) - 1:
                        # A video can arrive after a text sent just behind it; the
                        # next message (e.g. "send the cover photo") must come last.
                        time.sleep(VIDEO_PAUSE_SECONDS)


def report_failed(status):
    """Meta accepted a message but could not deliver it: say why in the log."""
    to = status.get("recipient_id")
    for error in status.get("errors") or [{}]:
        log.error("❌ A message to %s was not delivered: %s %s", mask_phone(to),
                  error.get("code"), error.get("title"))
        if error.get("code") == 131047:
            # More than 24 hours since this person last wrote to the bot.
            who = "the owner" if owner and to == owner.owner else "the customer"
            log.error("   %s hasn't written to the bot for 24 hours, so WhatsApp blocks "
                      "free messages. %s", who.capitalize(),
                      "Type אישורים to the bot to get the waiting albums again."
                      if who == "the owner" else "They must write first (see guide 3.1).")


def problem_notice(sender):
    """A short "technical problem, try again soon" message, not too often."""
    now = time.monotonic()
    if now - _last_problem_notice.get(sender, -PROBLEM_NOTICE_SECONDS) < PROBLEM_NOTICE_SECONDS:
        return []
    _last_problem_notice[sender] = now
    return [{"text": TEXTS["technical_problem"]}]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == WEBHOOK_PATH:
            self.verify_webhook(parse_qs(url.query))
        elif url.path == "/privacy":
            # Meta requires a public privacy policy before the app can be published.
            body = (PAGES_DIR / "privacy.html").read_bytes()
            self.respond(200, body, "text/html; charset=utf-8")
        elif url.path.startswith("/album/"):
            self.album_preview(url.path[len("/album/"):])
        elif url.path == "/health":
            self.respond(200, b"ok", "text/plain; charset=utf-8")
        else:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.respond(200, PAGE.format(time=now).encode("utf-8"), "text/html; charset=utf-8")

    def album_preview(self, rest):
        """The customer's album preview page, and its images (task 2.4)."""
        code, _, name = rest.partition("/")
        data = preview_links.find(code)
        if not data:
            body = preview_links.expired_html(TEXTS).encode("utf-8")
            self.respond(404, body, "text/html; charset=utf-8", private=True)
        elif not name:
            body = preview_links.page_html(code, data, TEXTS).encode("utf-8")
            self.respond(200, body, "text/html; charset=utf-8", private=True)
        else:
            path = preview_links.image_path(data, name)
            if path:
                self.respond(200, path.read_bytes(), "image/jpeg", private=True)
            else:
                self.respond(404, b"not found", "text/plain; charset=utf-8", private=True)

    def verify_webhook(self, query):
        """Meta's one-time check when we save the webhook address in its dashboard."""
        mode = query.get("hub.mode", [""])[0]
        token = query.get("hub.verify_token", [""])[0]
        challenge = query.get("hub.challenge", [""])[0]
        if mode == "subscribe" and hmac.compare_digest(token, env["WHATSAPP_VERIFY_TOKEN"]):
            log.info("Meta verified the webhook address ✅")
            self.respond(200, challenge.encode("utf-8"), "text/plain; charset=utf-8")
        else:
            log.warning("Webhook check failed: the verify token doesn't match .env")
            self.respond(403, b"forbidden", "text/plain; charset=utf-8")

    def do_POST(self):
        if urlparse(self.path).path != WEBHOOK_PATH:
            self.respond(404, b"not found", "text/plain; charset=utf-8")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY_BYTES:
            self.respond(413, b"too large", "text/plain; charset=utf-8")
            return
        body = self.rfile.read(length)
        if not is_from_meta(body, self.headers.get("X-Hub-Signature-256")):
            log.warning("Ignored a webhook with a wrong signature (not from Meta, "
                        "or WHATSAPP_APP_SECRET in .env is wrong)")
            self.respond(403, b"forbidden", "text/plain; charset=utf-8")
            return
        # Answer Meta right away, then reply to the customer in the background.
        # (If Meta waits too long, it sends the same notice again.)
        self.respond(200, b"ok", "text/plain; charset=utf-8")
        try:
            data = json.loads(body)
        except ValueError:
            log.warning("Got a webhook that isn't valid JSON")
            return
        threading.Thread(target=self.safe_handle, args=(data,), daemon=True).start()

    @staticmethod
    def safe_handle(data):
        try:
            handle_notice(data)
        except Exception:
            log.exception("Something went wrong while answering a message")

    def respond(self, status, body, content_type, private=False):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if private:
            # Customer photos: no copies kept on the way, not listed by search
            # engines, and the address isn't passed on to other sites.
            self.send_header("Cache-Control", "no-store, private")
            self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Turn off the default line-per-request log: it would include the
        # webhook check's secret token in the address.
        pass


def main():
    global whatsapp, db, orders, owner
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        sys.exit(f"❌ Missing in {ENV_FILE}: {', '.join(missing)}. See docs/setup/1.1-first-bot.md")
    whatsapp = WhatsApp(env)
    db = Database(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    orders = Orders(db)
    orders.send = send
    public_url = (env.get("PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")

    def make_link(result):
        code = preview_links.create(result["folder"], result["previews"], result["pages"],
                                    photos=result.get("photos_in_album"),
                                    design=result.get("design"),
                                    full_pages=result.get("full_pages"),
                                    photos_on_pages=result.get("photos_on_pages"),
                                    left_out=result.get("left_out"))
        return f"{public_url}/album/{code}"

    orders.on_ready = AlbumJobs(orders, send, TEXTS, make_link=make_link).start
    orders.on_cover = CoverChecks(orders, send, TEXTS).start
    owner = OwnerApprovals(orders, send, TEXTS, env.get("OWNER_PHONE"), public_url)
    orders.on_approval = owner.start
    orders.on_customer_text = owner.customer_text
    orders.on_payment = owner.payment                 # task 3.2
    orders.album_numbers = album_numbers              # task 3.2
    if not owner.owner:
        log.warning("OWNER_PHONE is not set in .env: albums can't be sent to you for "
                    "approval. See docs/setup/3.1-owner-approval.md")
    log.info("Bot running at http://localhost:%s (press Ctrl+C to stop)", PORT)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
