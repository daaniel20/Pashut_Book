"""Check photos for quality problems, and show the result (task 2.1).

Run from the project folder, with the project's Python (.venv, see the guide):

  .venv/bin/python album/check_photos.py ~/Desktop/test-photos
      checks every photo in a folder

  .venv/bin/python album/check_photos.py --order latest
      checks the photos of the newest order in Supabase (or give an order ID)

It prints a list in the Terminal, and makes a report page with small copies
of the photos: output/quality-report.html (open it with a double-click).
The report stays on the Mac only (the output folder is never uploaded).
"""

import base64
import html
import sys
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps

import quality

PROJECT_DIR = Path(__file__).resolve().parent.parent
REPORT = PROJECT_DIR / "output" / "quality-report.html"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
GRADE_TEXT = {"ok": "✅ ok", "small": "🟡 small spots only", "skip": "❌ leave out"}
GRADE_COLOR = {"ok": "#2e9e4f", "small": "#e0a800", "skip": "#d33"}


def photos_from_folder(folder):
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        sys.exit(f"❌ No such folder: {folder}")
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES)
    if not files:
        sys.exit(f"❌ No photos in {folder}")
    return [(p.name, p.read_bytes()) for p in files]


def photos_from_order(which):
    sys.path.insert(0, str(PROJECT_DIR / "server"))
    from database import Database, DatabaseError
    from settings import read_env

    env = read_env()
    db = Database(env["SUPABASE_URL"], env["SUPABASE_SECRET_KEY"])
    try:
        orders = db.recent_orders(20)
        if which == "latest":
            order = orders[0] if orders else None
        else:
            order = next((o for o in orders if o["id"].startswith(which)), None)
        if not order:
            sys.exit("❌ Order not found (only the 20 newest orders are searched).")
        rows = db.order_photos(order["id"])
        print(f"Order {order['id'][:8]}: downloading {len(rows)} photos…")
        return [(f"photo {row['number']:03d}", db.download(row["storage_path"]))
                for row in rows]
    except DatabaseError as error:
        sys.exit(f"❌ {error}")


def print_results(results):
    for r in results:
        problems = ", ".join(quality.PROBLEM_TEXT[p] for p in r.problems)
        if r.duplicate_of:
            problems += f" (keeps {r.duplicate_of})"
        print(f"  {GRADE_TEXT[r.grade]:<22} {r.name:<28} "
              f"{r.width}x{r.height}  sharp {r.sharpness:>6}  {problems}")
    counts = {grade: sum(r.grade == grade for r in results) for grade in GRADE_TEXT}
    dated = sum(r.taken is not None for r in results)
    print(f"\n{len(results)} photos: {counts['ok']} ok, {counts['small']} small spots only, "
          f"{counts['skip']} leave out.")
    print(f"{dated} have the date they were taken"
          + (" (sorted by it)." if dated else " (kept in the order received)."))
    located = sum(r.has_location for r in results)
    print(f"{located} still have a GPS location (only counted, never saved).")


def write_report(results, photos):
    data = dict(photos)
    cards = []
    for r in results:
        problems = "<br>".join(html.escape(quality.PROBLEM_TEXT[p]) for p in r.problems)
        if r.duplicate_of:
            problems += f"<br>keeps: {html.escape(r.duplicate_of)}"
        cards.append(f"""
<div class="card" style="border-color:{GRADE_COLOR[r.grade]}">
  {_thumbnail(data[r.name])}
  <b>{html.escape(r.name)}</b><br>
  {GRADE_TEXT[r.grade]}<br>
  <small>{r.width}×{r.height} · sharpness {r.sharpness}
  <br>{('📅 ' + r.taken.strftime('%d/%m/%Y')) if r.taken else 'no date'}
  · {'📍 has location' if r.has_location else 'no location'}</small><br>
  <span class="problems">{problems}</span>
</div>""")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Photo quality check</title>
<style>
 body {{ font-family: -apple-system, Arial, sans-serif; background:#f4f4f4; margin:20px; }}
 .card {{ display:inline-block; vertical-align:top; width:220px; margin:6px; padding:8px;
         background:white; border:5px solid; border-radius:8px; font-size:13px; }}
 .card img {{ width:220px; height:165px; object-fit:contain; background:#eee; display:block;
             margin-bottom:6px; }}
 .problems {{ color:#b00; }}
</style></head><body>
<h2>Photo quality check: {len(results)} photos, in album order</h2>
<p>Green = ok · Yellow = small spots only · Red = leave out</p>
<p>{sum(r.taken is not None for r in results)} of {len(results)} still have the date taken ·
{sum(r.has_location for r in results)} of {len(results)} still have a GPS location
(only checked yes/no; the place is never read or saved)</p>
{''.join(cards)}
</body></html>""", encoding="utf-8")


def _thumbnail(data):
    try:
        image = ImageOps.exif_transpose(Image.open(BytesIO(data))).convert("RGB")
        image.thumbnail((440, 330))
        buffer = BytesIO()
        image.save(buffer, "JPEG", quality=80)
        return f'<img src="data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}">'
    except Exception:
        return '<img alt="can\'t open">'


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--order":
        photos = photos_from_order(args[1])
    elif len(args) == 1 and not args[0].startswith("--"):
        photos = photos_from_folder(args[0])
    else:
        sys.exit(__doc__)
    print(f"Checking {len(photos)} photos…\n")
    results = quality.check_all(photos)
    print_results(results)
    write_report(results, photos)
    print(f"\nReport with the photos: {REPORT}")
    print(f"Open it:  open {REPORT}")


if __name__ == "__main__":
    main()
