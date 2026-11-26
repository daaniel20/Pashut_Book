"""Photo cleanup (task 3.4): customers' photos are deleted by themselves.

Why: photos are private, often of children (CLAUDE.md rule 5), and Supabase's
free plan holds only 1 GB (rule 11). So nothing is kept longer than needed.

What is deleted, and when (all three counted from the order's last moment):
- an album nobody paid for: UNPAID_DAYS (14) days after the customer's last
  message. The order is also closed ("cancelled" + note "expired"), so if the
  customer writes again they start a new album, with a short message saying
  the old one was deleted to protect their photos.
- a paid album: PAID_DAYS (30) days after the payment. There is no
  "delivered" step yet (printing comes later), so this leaves time to print,
  ship and reprint if something went wrong.
- a cancelled album (the customer started over): right away, an hour after
  it was cancelled (orders.py already deletes these after a minute; this
  catches the ones missed when the bot restarted at that moment).

Deleted each time: the photo files in the private Supabase bucket and their
rows, the album's folder on this Mac (output/albums/<order>/: pages, previews,
print PDFs) and its preview links. The order's row and its history stay (they
hold no photos), with the note "photos_deleted" and a history row
"photos_deleted" (how many files, why, after how many days).
Also: preview links that expired or lost their album, and the owner's photo
check report (output/quality-report.html, it has small copies of photos)
once it is UNPAID_DAYS old.

The bot runs this by itself, a few minutes after it starts and then every
CHECK_EVERY_HOURS hours. By hand on the Mac (shows what would be deleted,
deletes nothing):
    python3 server/cleanup.py
To really delete now:
    python3 server/cleanup.py --now
To clear old TEST albums sooner, e.g. unpaid ones idle for 1 day or more:
    python3 server/cleanup.py --unpaid-days 1 --now
(then restart the bot, so it forgets what it remembered about those albums).
Built-in Python only.
"""

import json
import logging
import shutil
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

from database import DatabaseError
from settings import PROJECT_DIR

log = logging.getLogger("bot")

UNPAID_DAYS = 14
PAID_DAYS = 30
CANCELLED_HOURS = 1
CHECK_EVERY_HOURS = 6
FIRST_CHECK_MINUTES = 3
ALBUMS_DIR = PROJECT_DIR / "output" / "albums"
LINKS_DIR = PROJECT_DIR / "output" / "preview-links"
REPORT = PROJECT_DIR / "output" / "quality-report.html"
FREE_STORAGE_MB = 1000


def _time(text):
    """Supabase's time text -> a datetime (or None)."""
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    # Python 3.9 (the Mac's) can't read 1-5 digits after the second's dot.
    if "." in text:
        head, _, rest = text.partition(".")
        digits = rest[:len(rest) - len(rest.lstrip("0123456789"))]
        text = head + "." + (digits + "000000")[:6] + rest[len(digits):]
    return datetime.fromisoformat(text)


def _iso(moment):
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def reason(row, now, unpaid_days=UNPAID_DAYS, paid_days=PAID_DAYS):
    """Why this order's photos should be deleted now: "cancelled", "unpaid",
    "paid", or None (keep them)."""
    updated = _time(row.get("updated_at")) or now
    if row["status"] == "cancelled":
        return "cancelled" if now - updated >= timedelta(hours=CANCELLED_HOURS) else None
    if row["status"] == "paid":
        paid = _time(row.get("paid_at")) or updated
        return "paid" if now - paid >= timedelta(days=paid_days) else None
    return "unpaid" if now - updated >= timedelta(days=unpaid_days) else None


def album_folder(order_id, albums_dir=ALBUMS_DIR):
    return albums_dir / order_id[:8]


def delete_local(order_id, albums_dir=ALBUMS_DIR, links_dir=LINKS_DIR):
    """Delete the album's folder on this Mac and its preview links.
    Returns True if there was something to delete."""
    folder = album_folder(order_id, albums_dir)
    found = False
    for link in links_dir.glob("*.json") if links_dir.exists() else []:
        try:
            if json.loads(link.read_text(encoding="utf-8")).get("folder") == str(folder):
                link.unlink()
                found = True
        except (OSError, ValueError):
            pass
    if folder.is_dir():
        shutil.rmtree(folder, ignore_errors=True)
        found = True
    return found


def old_links(links_dir=LINKS_DIR, now=None):
    """Delete preview links that expired or whose album is gone. Returns how many."""
    now = time.time() if now is None else now
    count = 0
    for link in links_dir.glob("*.json") if links_dir.exists() else []:
        try:
            data = json.loads(link.read_text(encoding="utf-8"))
            gone = now > data["expires"] or not (PROJECT_DIR / data["folder"]).is_dir()
        except (OSError, ValueError, KeyError, TypeError):
            gone = True
        if gone:
            link.unlink(missing_ok=True)
            count += 1
    return count


class Cleanup:
    """orders: the bot's orders.Orders (so a customer's remembered state is
    reloaded with the change), or None when run by hand."""

    def __init__(self, db, orders=None, history=None, albums_dir=ALBUMS_DIR,
                 links_dir=LINKS_DIR, report=REPORT):
        self.db = db
        self.orders = orders
        self.history = history
        self.albums_dir = albums_dir
        self.links_dir = links_dir
        self.report = report

    def due(self, now=None, unpaid_days=UNPAID_DAYS, paid_days=PAID_DAYS):
        """[(order row, reason)] of the orders to clean now."""
        now = now or datetime.now(timezone.utc)
        rows = self.db.orders_to_clean(_iso(now - timedelta(days=unpaid_days)),
                                       _iso(now - timedelta(days=paid_days)))
        return [(row, why) for row in rows or []
                for why in [reason(row, now, unpaid_days, paid_days)] if why]

    def run(self, now=None, unpaid_days=UNPAID_DAYS, paid_days=PAID_DAYS):
        """Clean everything that is due. Returns [(order row, reason, files deleted)].
        One order's problem never stops the others."""
        now = now or datetime.now(timezone.utc)
        done = []
        try:
            due = self.due(now, unpaid_days, paid_days)
        except DatabaseError as error:
            log.error("Cleanup: could not read the orders: %s", error)
            due = []
        for row, why in due:
            try:
                count = self.clean(row, why, now)
            except DatabaseError as error:
                log.error("Cleanup: could not delete the photos of %s: %s",
                          row["id"][:8], error)
                continue
            done.append((row, why, count))
        links = old_links(self.links_dir, now.timestamp())
        if links:
            log.info("Cleanup: deleted %s old preview links", links)
        if self.report.exists() and \
                now.timestamp() - self.report.stat().st_mtime > unpaid_days * 86400:
            self.report.unlink(missing_ok=True)
            log.info("Cleanup: deleted the old photo check report")
        return done

    def clean(self, row, why, now):
        """Delete one order's photos and album files and mark the order."""
        order_id = row["id"]
        count = self.db.delete_all_photos(order_id)
        local = delete_local(order_id, self.albums_dir, self.links_dir)
        notes = [n for n in row.get("notes") or []] + ["photos_deleted"]
        fields = {"notes": notes}
        if why == "unpaid":
            notes.append("expired")
            fields["status"] = "cancelled"

        def mark():
            self.db.update_order(order_id, fields)
        if self.orders:
            # The customer's remembered state is dropped and read again from
            # Supabase at their next message (with the change).
            self.orders.reload_after(row["phone"], order_id, mark)
        else:
            mark()
        days = (now - (_time(row.get("paid_at") if why == "paid" else None)
                       or _time(row.get("updated_at")) or now)).days
        self._record(order_id, row, count, why, days, local)
        log.info("Cleanup: deleted %s photos of order %s (%s, after %s days)%s",
                 count, order_id[:8], why, days, ", and its album files" if local else "")
        return count

    def _record(self, order_id, row, count, why, days, local):
        values = dict(count=count, detail=why, step=row.get("step"),
                      photos=row.get("photo_count"),
                      info={"days": days, "album_files": local})
        try:
            if self.orders:
                self.orders.record(order_id, "photos_deleted", **values)
            elif self.history:
                self.history.record(order_id, "photos_deleted", **values)
        except Exception:
            log.exception("Cleanup: could not record it in the order history")

    def start(self):
        """Run in the background: soon after the bot starts, then every few hours."""
        def loop():
            time.sleep(FIRST_CHECK_MINUTES * 60)
            while True:
                try:
                    self.run()
                except Exception:
                    log.exception("Cleanup failed; trying again later")
                time.sleep(CHECK_EVERY_HOURS * 3600)
        threading.Thread(target=loop, daemon=True, name="cleanup").start()


def main():
    from database import Database
    from history import History
    from settings import read_env

    args = sys.argv[1:]
    really = "--now" in args
    days = {"--unpaid-days": UNPAID_DAYS, "--paid-days": PAID_DAYS}
    for name in days:
        if name in args:
            try:
                days[name] = float(args[args.index(name) + 1])
            except (IndexError, ValueError):
                sys.exit(f"❌ {name} needs a number of days, e.g. {name} 1")
    env = read_env()
    if not env.get("SUPABASE_URL") or not env.get("SUPABASE_SECRET_KEY"):
        sys.exit("❌ SUPABASE_URL / SUPABASE_SECRET_KEY are missing in .env")
    db = Database(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    history = History(db, background=False)
    cleanup = Cleanup(db, history=history)
    unpaid, paid = days["--unpaid-days"], days["--paid-days"]
    try:
        count, size = db.photos_size()
        print(f"Supabase holds {count} photos, {size / 1e6:.0f} MB "
              f"(free plan: {FREE_STORAGE_MB} MB).")
        due = cleanup.due(unpaid_days=unpaid, paid_days=paid)
    except DatabaseError as error:
        sys.exit(f"❌ {error}")
    names = {"unpaid": f"not paid, no message for {unpaid:g}+ days",
             "paid": f"paid {paid:g}+ days ago", "cancelled": "cancelled"}
    if not due:
        print("Nothing to delete.")
    for row, why in due:
        print(f"  order {row['id'][:8]}: {row.get('photo_count') or 0} photos, "
              f"{row['status']}, {names[why]}")
    if not really:
        if due:
            print("Nothing was deleted. To delete these now, add --now")
        return
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    done = cleanup.run(unpaid_days=unpaid, paid_days=paid)
    print(f"✅ Deleted the photos of {len(done)} orders "
          f"({sum(count for _, _, count in done)} files).")
    count, size = db.photos_size()
    print(f"Supabase now holds {count} photos, {size / 1e6:.0f} MB.")
    if done:
        print("Now restart the bot, so it forgets those albums:  "
              "bash deploy/mac/install-bot-service.sh")


if __name__ == "__main__":
    main()
