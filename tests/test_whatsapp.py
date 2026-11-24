"""Automatic checks for sending a video with WhatsApp (the HD how-to clip).

No network: the calls to Meta are recorded instead of sent.
Run:   python3 -m unittest discover tests
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import whatsapp  # noqa: E402

ENV = {"WHATSAPP_PHONE_NUMBER_ID": "123", "WHATSAPP_ACCESS_TOKEN": "x"}


class FakeWhatsApp(whatsapp.WhatsApp):
    def __init__(self):
        super().__init__(ENV)
        self.calls = []

    def _call(self, url, data=None, timeout=20, content_type="application/json"):
        self.calls.append((url, data, content_type))
        if url.endswith("/media"):
            return json.dumps({"id": f"media-{len(self.calls)}"}).encode()
        return b"{}"


class VideoTest(unittest.TestCase):
    def setUp(self):
        self.clip = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        self.clip.write(b"not really a video")
        self.clip.close()
        self.wa = FakeWhatsApp()

    def tearDown(self):
        Path(self.clip.name).unlink()

    def sent(self):
        return json.loads(self.wa.calls[-1][1])

    def test_video_on_top_of_buttons(self):
        self.wa.send("972500000000", {"text": "how", "video_file": self.clip.name,
                                      "buttons": [{"id": "hd_continue", "title": "go"}]})
        payload = self.sent()["interactive"]
        self.assertEqual(payload["type"], "button")
        self.assertEqual(payload["header"]["type"], "video")
        self.assertEqual(payload["body"]["text"], "how")
        self.assertIn(b"video/mp4", self.wa.calls[0][1])     # uploaded as a video

    def test_video_with_caption(self):
        self.wa.send("972500000000", {"text": "steps", "video_file": self.clip.name})
        payload = self.sent()
        self.assertEqual(payload["type"], "video")
        self.assertEqual(payload["video"]["caption"], "steps")

    def test_uploaded_once(self):
        for _ in range(3):
            self.wa.send("972500000000", {"text": "x", "video_file": self.clip.name})
        uploads = [c for c in self.wa.calls if c[0].endswith("/media")]
        self.assertEqual(len(uploads), 1)


if __name__ == "__main__":
    unittest.main()
