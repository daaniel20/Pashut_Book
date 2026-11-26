"""Talk to our Supabase project (task 1.3): orders and photos.

Supabase gives us two things:
- a database with two tables, "orders" and "photos" (see supabase/1.3-orders-and-photos.sql)
- a PRIVATE storage bucket called "photos", where the photo files themselves go

This uses only Python's built-in tools (nothing to install). It talks to
Supabase's web address with the secret key from .env, which may read and
write everything, so the key must never leave the Mac.
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import quote

BUCKET = "photos"


class DatabaseError(Exception):
    """Supabase couldn't be reached, or refused a request."""


class Database:
    def __init__(self, url, secret_key, timeout=30):
        self.url = url.rstrip("/")
        self.key = secret_key
        self.timeout = timeout

    # ---------- orders ----------

    def latest_order(self, phone):
        """The customer's newest order, or None if they never wrote before."""
        rows = self._call("GET", "/rest/v1/orders?phone=eq." + quote(phone)
                          + "&order=created_at.desc&limit=1")
        return rows[0] if rows else None

    def get_order(self, order_id):
        rows = self._call("GET", "/rest/v1/orders?id=eq." + quote(order_id))
        return rows[0] if rows else None

    def create_order(self, phone, fields):
        rows = self._call("POST", "/rest/v1/orders", dict(fields, phone=phone),
                          prefer="return=representation")
        return rows[0]

    def update_order(self, order_id, fields):
        fields = dict(fields, updated_at=datetime.now(timezone.utc).isoformat())
        self._call("PATCH", "/rest/v1/orders?id=eq." + quote(order_id), fields,
                   prefer="return=minimal")

    def orders_with_note(self, note):
        """Orders whose notes include this note (e.g. "owner_check": waiting for
        the owner's approval, task 3.1), oldest first."""
        return self._call("GET", "/rest/v1/orders?select=id,phone,status&order=created_at"
                          "&notes=cs." + quote(json.dumps([note])))

    def orders_since(self, phone, since):
        """How many orders this phone number started since this time (ISO text),
        cancelled ones included (task 3.2: new albums per day)."""
        rows = self._call("GET", "/rest/v1/orders?select=id&phone=eq." + quote(phone)
                          + "&created_at=gte." + quote(since))
        return len(rows or [])

    def orders_to_clean(self, idle_before, paid_before):
        """Task 3.4: orders whose photos may need deleting (cleanup.py decides):
        cancelled ones, ones untouched since idle_before, ones paid before
        paid_before (times as ISO text). Orders already cleaned are skipped."""
        where = quote(f"(status.eq.cancelled,updated_at.lt.{idle_before},"
                      f"paid_at.lt.{paid_before})", safe="(),.:")
        return self._call("GET", "/rest/v1/orders?select=id,phone,status,step,notes,"
                          "photo_count,updated_at,paid_at&order=created_at"
                          "&notes=not.cs." + quote(json.dumps(["photos_deleted"]))
                          + "&or=" + where)

    def photos_size(self):
        """(how many photos are saved, their total size in bytes), for cleanup.py."""
        rows = self._call("GET", "/rest/v1/photos?select=size_bytes") or []
        return len(rows), sum(row.get("size_bytes") or 0 for row in rows)

    def recent_orders(self, limit=5):
        return self._call("GET", f"/rest/v1/orders?order=created_at.desc&limit={limit}"
                          "&select=id,phone,status,step,photo_count,created_at,photos(count)")

    # ---------- order history (task 3.3) ----------

    def add_event(self, row):
        """Add one row to the order history (history.py; numbers only)."""
        self._call("POST", "/rest/v1/order_events", row, prefer="return=minimal")

    def order_events(self, order_id):
        """An order's history, oldest first (for check_supabase.py)."""
        return self._call("GET", "/rest/v1/order_history?order_id=eq." + quote(order_id)
                          + "&select=created_at,event,step,photos,count,detail,"
                          "seconds_from_start&order=created_at,id")

    # ---------- photos ----------

    def add_photo(self, fields):
        """Record a photo. Returns the new row, or None if this photo
        (same WhatsApp ID) was already recorded."""
        rows = self._call("POST", "/rest/v1/photos?on_conflict=wa_media_id", fields,
                          prefer="return=representation,resolution=ignore-duplicates")
        return rows[0] if rows else None

    def update_photo_size(self, photo_id, size_bytes):
        self._call("PATCH", "/rest/v1/photos?id=eq." + quote(photo_id),
                   {"size_bytes": size_bytes}, prefer="return=minimal")

    def order_photos(self, order_id):
        """An order's saved photos (number and file path), in the order received."""
        return self._call("GET", "/rest/v1/photos?select=number,storage_path&order=number"
                          "&order_id=eq." + quote(order_id))

    def download(self, path):
        """Download one photo file from the private bucket (kept in memory)."""
        return self._call("GET", f"/storage/v1/object/{BUCKET}/{quote(path)}", as_bytes=True)

    def remove_photo_row(self, photo_id):
        self._call("DELETE", "/rest/v1/photos?id=eq." + quote(photo_id))

    def upload(self, path, data, mime_type):
        """Save one photo file in the private bucket."""
        self._call("POST", f"/storage/v1/object/{BUCKET}/{quote(path)}", raw=data,
                   content_type=mime_type, extra_headers={"x-upsert": "true"})

    def delete_order_photos(self, order_id, keep=None):
        """Delete all of an order's photo files and their rows. keep: the number
        of one photo to keep (the cover, when resending in HD, task 1.2b); it
        becomes photo 1, so the new photos are 2, 3, …"""
        rows = self._call("GET", "/rest/v1/photos?select=id,number,storage_path&order_id=eq."
                          + quote(order_id))
        kept = [row for row in rows if keep and row["number"] == keep]
        paths = [row["storage_path"] for row in rows if row not in kept]
        if paths:
            self._call("DELETE", f"/storage/v1/object/{BUCKET}", {"prefixes": paths})
        where = "/rest/v1/photos?order_id=eq." + quote(order_id)
        self._call("DELETE", where + (f"&number=neq.{keep}" if kept else ""))
        if kept and keep != 1:
            old = kept[0]["storage_path"]
            new = f"{order_id}/001" + old[old.rfind("."):]
            self._call("POST", "/storage/v1/object/move",
                       {"bucketId": BUCKET, "sourceKey": old, "destinationKey": new})
            self._call("PATCH", "/rest/v1/photos?id=eq." + quote(kept[0]["id"]),
                       {"number": 1, "storage_path": new})
        return len(paths)

    def delete_all_photos(self, order_id):
        """Task 3.4: delete every photo file of an order (also files that lost
        their row when saving failed half-way) and all its photo rows.
        Returns how many files were deleted."""
        rows = self._call("GET", "/rest/v1/photos?select=storage_path&order_id=eq."
                          + quote(order_id)) or []
        listed = self._call("POST", f"/storage/v1/object/list/{BUCKET}",
                            {"prefix": order_id, "limit": 1000}) or []
        paths = {row["storage_path"] for row in rows}
        paths |= {f"{order_id}/{item['name']}" for item in listed if item.get("id")}
        paths = sorted(paths)
        for start in range(0, len(paths), 100):
            self._call("DELETE", f"/storage/v1/object/{BUCKET}",
                       {"prefixes": paths[start:start + 100]})
        self._call("DELETE", "/rest/v1/photos?order_id=eq." + quote(order_id))
        return len(paths)

    def bucket(self):
        return self._call("GET", f"/storage/v1/bucket/{BUCKET}")

    # ---------- the actual web request ----------

    def _call(self, method, path, body=None, raw=None, prefer=None,
              content_type="application/json", extra_headers=None, as_bytes=False):
        headers = {
            "apikey": self.key,
            "Authorization": "Bearer " + self.key,
            "Content-Type": content_type,
        }
        if prefer:
            headers["Prefer"] = prefer
        headers.update(extra_headers or {})
        data = raw if raw is not None else (
            json.dumps(body).encode("utf-8") if body is not None else None)
        request = urllib.request.Request(self.url + path, data=data,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read()
        except urllib.error.HTTPError as error:
            # Supabase's error text explains the problem. It never contains the key.
            detail = error.read().decode("utf-8", "replace")[:300]
            raise DatabaseError(f"Supabase error {error.code} on {method} "
                                f"{path.split('?')[0]}: {detail}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise DatabaseError(f"Could not reach Supabase: {error}") from None
        if as_bytes:
            return text
        return json.loads(text) if text else None
