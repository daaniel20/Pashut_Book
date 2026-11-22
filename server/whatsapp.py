"""Talk to Meta's WhatsApp API: send messages, and download customers' photos.

Uses only Python's built-in tools. The token comes from .env.
"""

import json
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

    def send(self, to, message):
        """Send one WhatsApp message (text, or text with up to 3 buttons)."""
        if message.get("buttons"):
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
        self._call(f"{self.api}/{self.phone_number_id}/messages",
                   json.dumps(payload).encode("utf-8"))

    def photo_info(self, media_id):
        """Ask Meta where a customer's photo is. Returns url, mime_type, file_size.
        The download address works for 5 minutes only."""
        return json.loads(self._call(f"{self.api}/{media_id}"))

    def download(self, url):
        """Download the photo itself (it stays in memory, never on disk)."""
        return self._call(url, timeout=120)

    def _call(self, url, data=None, timeout=20):
        headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            headers["Content-Type"] = "application/json"
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
