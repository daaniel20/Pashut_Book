"""Talk to Meta's WhatsApp API: send messages, and download customers' photos.

Task 2.4: also send a message with a button that opens a web address (the
album's preview page), with a picture on top (the cover). The picture is first
uploaded to Meta, privately (it gets a number, not a public web address), then
sent. Meta deletes uploaded pictures by itself after 30 days.

Uses only Python's built-in tools. The token comes from .env.
"""

import json
import os
import threading
import time
import uuid
import urllib.error
import urllib.request

# Meta's API version. Each version works for about 2 years.
DEFAULT_GRAPH_VERSION = "v27.0"


class WhatsAppError(Exception):
    """Meta couldn't be reached, or refused a request."""


class WhatsApp:
    def __init__(self, env):
        version = env.get("WHATSAPP_GRAPH_VERSION") or DEFAULT_GRAPH_VERSION
        self.api = f"https://graph.facebook.com/{version}"
        self.phone_number_id = env["WHATSAPP_PHONE_NUMBER_ID"]
        self.token = env["WHATSAPP_ACCESS_TOKEN"]
        # Videos we send to everyone (the HD how-to clip) are uploaded once:
        # path -> (media ID, file's modified time, when uploaded).
        self._videos = {}
        self._videos_lock = threading.Lock()

    def send(self, to, message):
        """Send one WhatsApp message: text, text with up to 3 buttons,
        or text with a list (one button that opens up to 10 choices),
        or an image from this computer: {"image_file": path, "caption": "..."},
        or text with a button that opens a web address, optionally with an image on top:
        {"text": "...", "link": {"button": "...", "url": "..."}, "image_file": path},
        or a short video from this computer on top of the text (with or without
        buttons): {"text": "...", "video_file": path, "buttons": [...]}."""
        if message.get("video_file") and message.get("buttons"):
            payload = {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "header": {"type": "video", "video": {"id": self.video_id(message["video_file"])}},
                    "body": {"text": message["text"]},
                    "action": {"buttons": [
                        {"type": "reply", "reply": button} for button in message["buttons"]
                    ]},
                },
            }
        elif message.get("video_file"):
            payload = {"type": "video", "video": {
                "id": self.video_id(message["video_file"]),
                "caption": message["text"],
            }}
        elif message.get("link"):
            interactive = {
                "type": "cta_url",
                "body": {"text": message["text"]},
                "action": {"name": "cta_url", "parameters": {
                    "display_text": message["link"]["button"],
                    "url": message["link"]["url"],
                }},
            }
            if message.get("image_file"):
                interactive["header"] = {"type": "image", "image": {
                    "id": self.upload_image(message["image_file"])}}
            payload = {"type": "interactive", "interactive": interactive}
        elif message.get("image_file"):
            payload = {"type": "image", "image": {
                "id": self.upload_image(message["image_file"]),
                "caption": message.get("caption", ""),
            }}
        elif message.get("list"):
            menu = message["list"]
            payload = {
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "body": {"text": message["text"]},
                    "action": {"button": menu["button"], "sections": [
                        {"title": menu["title"], "rows": menu["rows"]}
                    ]},
                },
            }
        elif message.get("buttons"):
            payload = {
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": message["text"]},
                    "action": {"buttons": [
                        {"type": "reply", "reply": button} for button in message["buttons"]
                    ]},
                },
            }
        else:
            payload = {"type": "text", "text": {"body": message["text"]}}
        payload.update({"messaging_product": "whatsapp", "to": to})
        answer = self._call(f"{self.api}/{self.phone_number_id}/messages",
                            json.dumps(payload).encode("utf-8"))
        # WhatsApp's ID for this message: its "delivered" and "read" reports
        # carry the same ID (task 3.3b).
        try:
            return json.loads(answer)["messages"][0]["id"]
        except (ValueError, KeyError, IndexError, TypeError):
            return None

    def video_id(self, path):
        """The media ID of a video, uploaded to Meta once and reused. Meta keeps
        uploads for 30 days, so it's uploaded again after 25 days, or if the file changed."""
        changed = os.path.getmtime(path)
        with self._videos_lock:
            known = self._videos.get(path)
            if known and known[1] == changed and time.time() - known[2] < 25 * 24 * 3600:
                return known[0]
            media_id = self.upload_image(path, mime="video/mp4", filename="clip.mp4")
            self._videos[path] = (media_id, changed, time.time())
            return media_id

    def upload_image(self, path, mime="image/jpeg", filename="page.jpg"):
        """Upload a JPEG image (or another file type) to Meta. Returns its media ID."""
        with open(path, "rb") as file:
            data = file.read()
        # A "multipart" form: the way websites upload files.
        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("messaging_product", "whatsapp"), ("type", mime)):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                         f'\r\n\r\n{value}\r\n'.encode("utf-8"))
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                     f'filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode("utf-8"))
        body = b"".join(parts) + data + f"\r\n--{boundary}--\r\n".encode("utf-8")
        answer = self._call(f"{self.api}/{self.phone_number_id}/media", body, timeout=60,
                            content_type=f"multipart/form-data; boundary={boundary}")
        return json.loads(answer)["id"]

    def photo_info(self, media_id):
        """Ask Meta where a customer's photo is. Returns url, mime_type, file_size.
        The download address works for 5 minutes only."""
        return json.loads(self._call(f"{self.api}/{media_id}"))

    def download(self, url):
        """Download the photo itself (it stays in memory, never on disk)."""
        return self._call(url, timeout=120)

    def _call(self, url, data=None, timeout=20, content_type="application/json"):
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(url, data=data, headers=headers,
                                         method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            # Meta's error text explains the problem (e.g. expired token).
            # It never contains the token itself.
            detail = error.read().decode("utf-8", "replace")[:300]
            raise WhatsAppError(f"Meta error {error.code}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise WhatsAppError(f"Could not reach Meta: {error}") from None
