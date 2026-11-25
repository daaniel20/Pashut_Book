"""Automatic checks for building the album from the bot (task 2.2).

The real album tool is replaced by a pretend one, so no photos or Pillow are needed.
Run:   python3 -m unittest discover tests
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

import album_job  # noqa: E402
from settings import load_texts  # noqa: E402

TEXTS = load_texts("he")
PHONE = "972500000000"


class FakeOrders:
    def __init__(self, notes=()):
        self.notes = list(notes)
        self.asked = False
        self.current = True    # the customer hasn't started another order
        self.done = True       # and isn't in the middle of changing something

    def wait_for_photos(self, order_id, timeout):
        return True

    def notes_of(self, phone, order_id):
        return list(self.notes) if self.current else None

    def is_done(self, phone, order_id):
        return self.current and self.done

    def add_note(self, phone, order_id, note):
        self.notes.append(note)

    def ask_hd(self, phone, order_id):
        self.asked = True
        self.notes.append("hd_asked")
        return True


class AlbumJobTest(unittest.TestCase):
    def run_job(self, check, notes=(), current=True, built=None, done=True, fail_at=None):
        self.orders = FakeOrders(notes)
        self.orders.current = current
        self.orders.done = done
        self.sent, self.calls = [], []

        def tool(order_id, check_only):
            self.calls.append("check" if check_only else "build")
            return check if check_only else (built or {"pages": 24, "folder": "x"})

        def send(phone, message):
            if fail_at is not None and len(self.sent) == fail_at:
                return False
            self.sent.append(message)
            return True

        jobs = album_job.AlbumJobs(self.orders, send, TEXTS, run_tool=tool,
                                   make_link=lambda result: "https://x/album/CODE")
        jobs.run(PHONE, "order-1")

    def built(self):
        groups = [[], [1], [2, 3], [4]]
        return {"pages": 4, "folder": "x",
                "previews": [{"file": f"p{i}.jpg", "pages": g} for i, g in enumerate(groups)]}

    def test_one_link_is_sent_after_building(self):
        self.run_job(self.info(), built=self.built())
        self.assertEqual(len(self.sent), 2)
        self.assertIn("4", self.sent[0]["text"])
        self.assertEqual(self.sent[0]["link"]["url"], "https://x/album/CODE")
        self.assertEqual(self.sent[0]["image_file"], "p0.jpg")    # the cover on top
        self.assertEqual(self.sent[-1]["buttons"][0]["id"], "preview_ok")
        self.assertIn("previews_sent", self.orders.notes)

    def test_no_previews_while_the_customer_is_changing_something(self):
        self.run_job(self.info(), built=self.built(), done=False)
        self.assertEqual(self.sent, [])
        self.assertNotIn("previews_sent", self.orders.notes)

    def test_a_failed_link_stops_there(self):
        self.run_job(self.info(), built=self.built(), fail_at=0)
        self.assertEqual(self.sent, [])
        self.assertNotIn("previews_sent", self.orders.notes)

    def info(self, photos=60, without_hd=0, blurry=0, duplicate=0):
        return {"photos": photos, "used": photos - blurry - duplicate, "without_hd": without_hd,
                "left_out": {"blurry": blurry, "duplicate": duplicate, "unusable": 0}}

    def test_good_photos_build_quietly(self):
        self.run_job(self.info())
        self.assertEqual(self.calls, ["check", "build"])
        self.assertEqual(self.sent, [])

    def test_left_out_photos_get_one_short_message(self):
        self.run_job(self.info(blurry=3, duplicate=2))
        self.assertEqual(self.calls, ["check", "build"])
        self.assertEqual(len(self.sent), 1)
        self.assertIn("3 תמונות מטושטשות ו-2 תמונות כפולות", self.sent[0]["text"])

    def test_no_hd_asks_before_building(self):
        self.run_job(self.info(without_hd=50, blurry=2))
        self.assertTrue(self.orders.asked)
        self.assertEqual(self.calls, ["check"])          # not built yet
        self.assertEqual([b["id"] for b in self.sent[0]["buttons"]], ["hd_help", "hd_continue"])

    def test_no_hd_asks_only_once(self):
        self.run_job(self.info(without_hd=60), notes=["hd_asked"])
        self.assertFalse(self.orders.asked)
        self.assertEqual(self.calls, ["check", "build"])

    def test_a_few_photos_without_hd_are_fine(self):
        self.run_job(self.info(without_hd=10))
        self.assertFalse(self.orders.asked)

    def test_customer_moved_on(self):
        self.run_job(self.info(), current=False)
        self.assertEqual(self.calls, ["check"])
        self.assertEqual(self.sent, [])

    def test_tool_missing_or_failed(self):
        self.run_job(None)
        self.assertEqual(self.calls, ["check"])
        self.assertEqual(self.sent, [])



class RebuildTest(unittest.TestCase):
    def test_change_during_a_build_builds_again(self):
        import threading
        builds = []
        first_build_started, let_it_finish = threading.Event(), threading.Event()
        info = {"photos": 10, "used": 10, "without_hd": 0,
                "left_out": {"blurry": 1, "duplicate": 0, "unusable": 0}}

        def tool(order_id, check_only):
            if check_only:
                return info
            builds.append(order_id)
            if len(builds) == 1:
                first_build_started.set()
                let_it_finish.wait(5)
            return {"pages": 24, "folder": "x"}

        sent = []
        jobs = album_job.AlbumJobs(FakeOrders(), lambda phone, m: sent.append(m),
                                   TEXTS, run_tool=tool)
        jobs.start(PHONE, "order-1")
        self.assertTrue(first_build_started.wait(5))
        jobs.start(PHONE, "order-1")   # the customer changed the title meanwhile
        let_it_finish.set()
        for _ in range(100):
            with jobs._guard:
                if "order-1" not in jobs._running:
                    break
            threading.Event().wait(0.05)
        self.assertEqual(len(builds), 2)
        self.assertEqual(len(sent), 1)  # "1 blurry photo left out" is said once



class AlbumNumbersTest(unittest.TestCase):
    """Task 3.2: the photo numbers inside the album, to check what the customer types."""

    def test_numbers_from_the_layout(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            real = album_job.PROJECT_DIR
            album_job.PROJECT_DIR = Path(folder)
            try:
                self.assertIsNone(album_job.album_numbers("abcdef12-0000"))
                albums = Path(folder) / "output" / "albums" / "abcdef12"
                albums.mkdir(parents=True)
                (albums / "layout.json").write_text(json.dumps({
                    "cover": {"spots": [{"photo": "photo 001"}]},
                    "pages": [{"spots": [{"photo": "photo 002"}, {"photo": "photo 015"}]},
                              {"spots": []}]}))
                self.assertEqual(album_job.album_numbers("abcdef12-0000"), {2, 15})
            finally:
                album_job.PROJECT_DIR = real


if __name__ == "__main__":
    unittest.main()
