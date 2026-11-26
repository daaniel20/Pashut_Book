"""Automatic checks for the photo cleanup (task 3.4).

Uses a pretend Supabase and a temporary folder for the album files, so it needs
no internet and touches nothing real.
Run:   python3 -m unittest discover tests
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cleanup  # noqa: E402
import orders  # noqa: E402
from database import DatabaseError  # noqa: E402
from settings import load_texts  # noqa: E402
from test_orders import FakeDatabase  # noqa: E402

TEXTS = load_texts("he")
PHONE = "972500000000"
NOW = datetime(2026, 12, 20, 12, 0, tzinfo=timezone.utc)


def ago(days=0, hours=0):
    return (NOW - timedelta(days=days, hours=hours)).isoformat()


class CleanupDatabase(FakeDatabase):
    def __init__(self):
        super().__init__()
        self.events = []

    def orders_to_clean(self, idle_before, paid_before):
        self._check()
        return [dict(o) for o in self.orders if "photos_deleted" not in o.get("notes", [])]

    def delete_all_photos(self, order_id):
        self._check()
        paths = {p["storage_path"] for p in self.photos if p["order_id"] == order_id}
        paths |= {f for f in self.files if f.startswith(order_id + "/")}
        for path in paths:
            self.files.pop(path, None)
        self.photos = [p for p in self.photos if p["order_id"] != order_id]
        return len(paths)

    def add_event(self, row):
        self.events.append(row)


class History:
    def __init__(self):
        self.rows = []

    def record(self, order_id, event, **values):
        self.rows.append(dict(values, order_id=order_id, event=event))


class ReasonTest(unittest.TestCase):
    def row(self, status, updated, paid=None):
        return {"status": status, "updated_at": updated, "paid_at": paid}

    def test_unpaid_after_14_days(self):
        self.assertIsNone(cleanup.reason(self.row("ready", ago(13)), NOW))
        self.assertEqual(cleanup.reason(self.row("ready", ago(14)), NOW), "unpaid")
        self.assertEqual(cleanup.reason(self.row("approved", ago(20)), NOW), "unpaid")
        self.assertEqual(cleanup.reason(self.row("collecting", ago(15)), NOW), "unpaid")

    def test_paid_30_days_after_payment(self):
        self.assertIsNone(cleanup.reason(self.row("paid", ago(40), ago(29)), NOW))
        self.assertEqual(cleanup.reason(self.row("paid", ago(2), ago(31)), NOW), "paid")

    def test_cancelled_after_an_hour(self):
        self.assertIsNone(cleanup.reason(self.row("cancelled", ago(hours=0.5)), NOW))
        self.assertEqual(cleanup.reason(self.row("cancelled", ago(hours=2)), NOW), "cancelled")

    def test_supabase_times(self):
        """Supabase sends e.g. 5 digits after the dot; the Mac's Python 3.9 must read it."""
        self.assertEqual(cleanup._time("2026-11-26T10:00:00.12345+00:00"),
                         datetime(2026, 11, 26, 10, 0, 0, 123450, tzinfo=timezone.utc))
        self.assertEqual(cleanup._time("2026-11-26T10:00:00Z").hour, 10)


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.db = CleanupDatabase()
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.albums, self.links = root / "albums", root / "links"
        self.links.mkdir()
        self.history = History()
        self.orders = orders.Orders(self.db)
        self.orders.history = self.history
        self.cleanup = cleanup.Cleanup(self.db, self.orders, albums_dir=self.albums,
                                       links_dir=self.links, report=root / "report.html")

    def tearDown(self):
        self.tmp.cleanup()

    def order(self, status, step, days, paid_days=None, photos=3, phone=PHONE, notes=()):
        order_id = f"{len(self.db.orders):08d}-0000-0000-0000-000000000000"
        self.db.orders.append({"id": order_id, "phone": phone, "status": status, "step": step,
                               "design": "classic", "title": None, "photo_count": photos,
                               "notes": list(notes), "updated_at": ago(days),
                               "paid_at": ago(paid_days) if paid_days is not None else None})
        for n in range(1, photos + 1):
            path = f"{order_id}/{n:03d}.jpg"
            self.db.photos.append({"id": f"{order_id}-{n}", "order_id": order_id, "number": n,
                                   "storage_path": path})
            self.db.files[path] = b"photo"
        folder = self.albums / order_id[:8]
        (folder / "preview").mkdir(parents=True)
        (folder / "print-pages.pdf").write_bytes(b"pdf")
        (self.links / f"{order_id[:8]}.json").write_text(json.dumps(
            {"folder": str(folder), "expires": NOW.timestamp() + 3600}))
        return order_id

    def files_of(self, order_id):
        return [f for f in self.db.files if f.startswith(order_id)]

    def test_only_old_orders_are_cleaned(self):
        old = self.order("ready", "done", 15)
        new = self.order("ready", "done", 3, phone="972500000001")
        paid_old = self.order("paid", "paid", 31, paid_days=31, phone="972500000002")
        paid_new = self.order("paid", "paid", 5, paid_days=5, phone="972500000003")
        done = self.cleanup.run(NOW)
        self.assertEqual(sorted((r["id"], why, n) for r, why, n in done),
                         sorted([(old, "unpaid", 3), (paid_old, "paid", 3)]))
        for kept in (new, paid_new):
            self.assertEqual(len(self.files_of(kept)), 3)
            self.assertTrue((self.albums / kept[:8]).exists())
            self.assertTrue((self.links / f"{kept[:8]}.json").exists())
        for gone in (old, paid_old):
            self.assertEqual(self.files_of(gone), [])
            self.assertFalse((self.albums / gone[:8]).exists())
            self.assertFalse((self.links / f"{gone[:8]}.json").exists())
        rows = {o["id"]: o for o in self.db.orders}
        self.assertEqual(rows[old]["status"], "cancelled")
        self.assertIn("expired", rows[old]["notes"])
        self.assertEqual(rows[paid_old]["status"], "paid")   # a paid order stays paid
        self.assertIn("photos_deleted", rows[paid_old]["notes"])
        self.assertNotIn("expired", rows[paid_old]["notes"])
        # Each is cleaned once only.
        self.assertEqual(self.cleanup.run(NOW), [])

    def test_recorded_in_the_history(self):
        old = self.order("ready", "done", 20)
        self.cleanup.run(NOW)
        row = next(r for r in self.history.rows if r["event"] == "photos_deleted")
        self.assertEqual((row["order_id"], row["count"], row["detail"]), (old, 3, "unpaid"))
        self.assertEqual(row["info"], {"days": 20, "album_files": True})

    def test_files_without_a_row_are_deleted_too(self):
        old = self.order("cancelled", "photos", 1)
        self.db.files[f"{old}/009.jpg"] = b"saving failed half-way"
        self.assertEqual(self.cleanup.run(NOW)[0][2], 4)
        self.assertEqual(self.files_of(old), [])

    def test_one_failure_does_not_stop_the_rest(self):
        self.order("ready", "done", 20)
        self.db.down = True
        self.assertEqual(self.cleanup.run(NOW), [])   # no crash
        self.db.down = False
        self.assertEqual(len(self.cleanup.run(NOW)), 1)

    def test_customer_returns_after_expiry(self):
        """The customer's remembered state is dropped; their next message starts
        a new album, with one message saying why the old one is gone."""
        self.orders.answer(PHONE, "text", "שלום", TEXTS)
        old = self.db.orders[-1]["id"]
        self.db.orders[-1].update(updated_at=ago(15), photo_count=3)
        self.cleanup.run(NOW)
        replies, _ = self.orders.answer(PHONE, "text", "שלום", TEXTS)
        self.assertIn("נמחק", replies[0]["text"])
        self.assertIn("14", replies[0]["text"])
        self.assertNotEqual(self.db.orders[-1]["id"], old)
        replies, _ = self.orders.answer(PHONE, "text", "שלום", TEXTS)
        self.assertFalse(any("נמחק" in r.get("text", "") for r in replies))

    def test_old_links_and_report(self):
        (self.links / "expired.json").write_text(json.dumps(
            {"folder": str(self.albums / "x"), "expires": NOW.timestamp() - 10}))
        (self.links / "broken.json").write_text("not json")
        report = Path(self.tmp.name) / "report.html"
        report.write_text("thumbnails")
        self.cleanup.run(NOW)
        self.assertFalse((self.links / "expired.json").exists())
        self.assertFalse((self.links / "broken.json").exists())
        self.assertFalse(report.exists())   # NOW is weeks after the file was written

    def test_database_error_reading_orders(self):
        self.db.down = True
        try:
            self.assertEqual(self.cleanup.run(NOW), [])
        except DatabaseError:
            self.fail("a Supabase problem must not stop the bot")


if __name__ == "__main__":
    unittest.main()
