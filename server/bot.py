"""The Pashut Book WhatsApp bot (task 1.1: answers every message with "Hello").

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
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from settings import ENV_FILE, load_texts, read_env

# 127.0.0.1 = "this computer only". Only the Cloudflare Tunnel (on the same Mac)
# can reach it, never other devices on the home Wi-Fi.
HOST = "127.0.0.1"
PORT = 8000
WEBHOOK_PATH = "/webhook"
# Meta's API version. Each version works for about 2 years.
DEFAULT_GRAPH_VERSION = "v23.0"
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
]

env = read_env()
TEXTS = load_texts("he")

# Meta sometimes sends the same message twice. Remember recent message IDs
# so the customer gets one reply, not two.
_seen_ids = deque(maxlen=1000)
_seen_lock = threading.Lock()

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


def send_text(to, text):
    """Send a WhatsApp text message through Meta's API."""
    version = env.get("WHATSAPP_GRAPH_VERSION") or DEFAULT_GRAPH_VERSION
    url = f"https://graph.facebook.com/{version}/{env['WHATSAPP_PHONE_NUMBER_ID']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text},
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {env['WHATSAPP_ACCESS_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            log.info("Reply sent to %s", mask_phone(to))
    except urllib.error.HTTPError as error:
        # Meta's error text explains the problem (e.g. expired token). It never
        # contains the token itself.
        detail = error.read().decode("utf-8", "replace")[:500]
        log.error("Meta refused the reply (error %s): %s", error.code, detail)
    except urllib.error.URLError as error:
        log.error("Could not reach Meta: %s", error.reason)


def handle_notice(data):
    """Read one webhook notice from Meta and answer any new messages in it."""
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            # "statuses" = delivery reports (sent / delivered / read). Ignore.
            for message in value.get("messages", []):
                sender = message.get("from")
                message_id = message.get("id")
                if not sender or not message_id or not is_new_message(message_id):
                    continue
                # We log only the message type, never its text or photos.
                log.info("Got a %s message from %s", message.get("type"), mask_phone(sender))
                send_text(sender, TEXTS["hello"])


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlparse(self.path)
        if url.path == WEBHOOK_PATH:
            self.verify_webhook(parse_qs(url.query))
        elif url.path == "/health":
            self.respond(200, b"ok", "text/plain; charset=utf-8")
        else:
            now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.respond(200, PAGE.format(time=now).encode("utf-8"), "text/html; charset=utf-8")

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

    def respond(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        # Turn off the default line-per-request log: it would include the
        # webhook check's secret token in the address.
        pass


def main():
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        sys.exit(f"❌ Missing in {ENV_FILE}: {', '.join(missing)}. See docs/setup/1.1-first-bot.md")
    log.info("Bot running at http://localhost:%s (press Ctrl+C to stop)", PORT)
    try:
        ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
