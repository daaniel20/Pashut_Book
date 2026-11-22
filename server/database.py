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

    def create_order(self, phone, fields):
        rows = self._call("POST", "/rest/v1/orders", dict(fields, phone=phone),
                          prefer="return=representation")
        return rows[0]

    def update_order(self, order_id, fields):
        fields = dict(fields, updated_at=datetime.now(timezone.utc).isoformat())
        self._call("PATCH", "/rest/v1/orders?id=eq." + quote(order_id), fields,
                   prefer="return=minimal")

    def recent_orders(self, limit=5):
        return self._call("GET", f"/rest/v1/orders?order=created_at.desc&limit={limit}"
                          "&select=id,phone,status,step,photo_count,created_at,photos(count)")

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

    def remove_photo_row(self, photo_id):
        self._call("DELETE", "/rest/v1/photos?id=eq." + quote(photo_id))

    def upload(self, path, data, mime_type):
        """Save one photo file in the private bucket."""
        self._call("POST", f"/storage/v1/object/{BUCKET}/{quote(path)}", raw=data,
                   content_type=mime_type, extra_headers={"x-upsert": "true"})

    def delete_order_photos(self, order_id):
        """Delete all of an order's photo files and their rows."""
        rows = self._call("GET", "/rest/v1/photos?select=storage_path&order_id=eq."
                          + quote(order_id))
        paths = [row["storage_path"] for row in rows]
        if paths:
            self._call("DELETE", f"/storage/v1/object/{BUCKET}", {"prefixes": paths})
        self._call("DELETE", "/rest/v1/photos?order_id=eq." + quote(order_id))
        return len(paths)

    def bucket(self):
        return self._call("GET", f"/storage/v1/bucket/{BUCKET}")

    # ---------- the actual web request ----------

    def _call(self, method, path, body=None, raw=None, prefer=None,
              content_type="application/json", extra_headers=None):
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
        return json.loads(text) if text else None
